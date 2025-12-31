"""
Quantum HUB - LangGraph Orchestrator

The central AI-driven Hub that implements the Supervisor Pattern for
coordinating spoke services using Fan-Out/Fan-In parallel execution.

This is the core innovation of Quantum HUB ERP - replacing linear workflows
with parallel, agentic orchestration.
"""

import json
import operator
from datetime import datetime
from typing import Annotated, Any, Optional, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db_context
from services.inventory import InventoryService
from services.scheduling import SchedulingService
from services.costing import CostingService
from services.job import JobService
from services.conversation import ConversationService
from models import QuoteType, Item


# ============================================================================
# Agent State Definition
# ============================================================================

class AgentState(TypedDict):
    """State shared across all nodes in the graph."""
    # Message history
    messages: Annotated[list, operator.add]

    # Conversation context
    thread_id: Optional[str]
    conversation_history: Optional[list]

    # Routing control
    next_step: str
    intent: str

    # Job context
    job_id: Optional[int]
    customer_name: Optional[str]
    product_description: Optional[str]
    requested_date: Optional[str]
    quantity: Optional[int]

    # BOM for quoting
    bom: Optional[list[dict]]
    labor_hours: Optional[float]
    machine_type: Optional[str]

    # Quote selection (for accepting quotes)
    quote_selection: Optional[str]
    pending_quote_data: Optional[dict]

    # Parallel execution results (Fan-In collection)
    inventory_data: Optional[dict]
    schedule_data: Optional[dict]
    cost_data: Optional[dict]

    # Final output
    quote_options: Optional[dict]
    response_type: Optional[str]
    response_data: Optional[dict]

    # Error handling
    error: Optional[str]


# ============================================================================
# System Prompts
# ============================================================================

SUPERVISOR_SYSTEM_PROMPT = """You are the Quantum HUB Supervisor - an AI orchestrator for a manufacturing ERP system.

Your role is to:
1. Understand user intent from natural language
2. Route requests to appropriate analysis workflows
3. Synthesize results into actionable options

You support these primary workflows:
- QUOTE_REQUEST: User wants a quote for manufacturing a product
- SCHEDULE_REQUEST: User wants to schedule production (Dynamic Entry - no PO required)
- JOB_STATUS: User wants status on an existing job
- INVENTORY_QUERY: User wants to check specific item stock (e.g., "do we have aluminum?")
- LIST_INVENTORY: User wants to see all inventory items (e.g., "show inventory", "list materials")
- SCHEDULE_VIEW: User wants to see production schedule
- ACCEPT_QUOTE: User wants to accept a quote option (e.g., "accept the balanced option", "go with fastest")
- GENERAL_QUERY: General questions about the system

Extract these details from the user message when applicable:
- customer_name: Who is the customer
- product_description: What they want manufactured
- quantity: How many units
- requested_date: When they need it
- job_number: If referencing an existing job
- material_type: If mentioned (e.g., "aluminum 6061", "steel")
- quote_selection: If accepting a quote, which option ("fastest", "cheapest", "balanced")

Respond with a JSON object containing:
{{
    "intent": "QUOTE_REQUEST|SCHEDULE_REQUEST|JOB_STATUS|INVENTORY_QUERY|LIST_INVENTORY|SCHEDULE_VIEW|ACCEPT_QUOTE|GENERAL_QUERY",
    "customer_name": "extracted name or null",
    "product_description": "what to manufacture or null",
    "quantity": number or null,
    "requested_date": "date string or null",
    "job_number": "if referenced or null",
    "material_type": "if mentioned or null",
    "quote_selection": "fastest|cheapest|balanced or null",
    "clarification_needed": "question to ask if more info needed or null"
}}"""

SYNTHESIZER_SYSTEM_PROMPT = """You are the Quote Synthesizer for Quantum HUB ERP.

You receive analysis results from three parallel systems:
1. Inventory Analysis - stock availability and restock times
2. Scheduling Analysis - machine availability and production slots
3. Costing Analysis - price calculations with options

Your job is to synthesize these into a clear, actionable response for the user.

Present THREE options:
1. FASTEST: Prioritize speed, may cost more
2. CHEAPEST: Prioritize cost savings, may take longer
3. BALANCED: Optimal trade-off (recommended)

For each option, clearly state:
- Total price
- Delivery date
- Key trade-offs

Be concise but informative. Manufacturing managers are busy."""


# ============================================================================
# Hub Implementation
# ============================================================================

class QuantumHub:
    """
    The Quantum HUB LangGraph Orchestrator.

    Implements Supervisor Pattern with Fan-Out/Fan-In parallel execution
    for the Parallel Quoting workflow.
    """

    def __init__(self):
        settings = get_settings()

        # Initialize LLM
        self.llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            anthropic_api_key=settings.anthropic_api_key,
            temperature=0.1,
        )

        # Build the graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""

        # Create the graph
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("inventory_check", self._inventory_node)
        workflow.add_node("scheduling_check", self._scheduling_node)
        workflow.add_node("costing_check", self._costing_node)
        workflow.add_node("synthesizer", self._synthesizer_node)
        workflow.add_node("job_status", self._job_status_node)
        workflow.add_node("schedule_view", self._schedule_view_node)
        workflow.add_node("direct_response", self._direct_response_node)
        workflow.add_node("create_job", self._create_job_node)
        workflow.add_node("list_inventory", self._list_inventory_node)
        workflow.add_node("accept_quote", self._accept_quote_node)

        # Set entry point
        workflow.set_entry_point("supervisor")

        # Add conditional routing from supervisor
        workflow.add_conditional_edges(
            "supervisor",
            self._route_from_supervisor,
            {
                "parallel_analysis": "inventory_check",
                "job_status": "job_status",
                "schedule_view": "schedule_view",
                "create_job": "create_job",
                "list_inventory": "list_inventory",
                "accept_quote": "accept_quote",
                "direct_response": "direct_response",
                "end": END,
            }
        )

        # Fan-out: inventory_check leads to scheduling_check (in sequence for now)
        # Note: True parallel would use asyncio.gather in production
        workflow.add_edge("inventory_check", "scheduling_check")
        workflow.add_edge("scheduling_check", "costing_check")

        # Fan-in: all analysis nodes lead to synthesizer
        workflow.add_edge("costing_check", "synthesizer")

        # Terminal nodes
        workflow.add_edge("synthesizer", END)
        workflow.add_edge("job_status", END)
        workflow.add_edge("schedule_view", END)
        workflow.add_edge("create_job", END)
        workflow.add_edge("list_inventory", END)
        workflow.add_edge("accept_quote", END)
        workflow.add_edge("direct_response", END)

        return workflow.compile()

    def _route_from_supervisor(self, state: AgentState) -> str:
        """Route based on supervisor's intent classification."""
        intent = state.get("intent", "").upper()

        if intent == "QUOTE_REQUEST":
            return "parallel_analysis"
        elif intent == "SCHEDULE_REQUEST":
            return "create_job"
        elif intent == "JOB_STATUS":
            return "job_status"
        elif intent == "SCHEDULE_VIEW":
            return "schedule_view"
        elif intent == "LIST_INVENTORY":
            return "list_inventory"
        elif intent == "INVENTORY_QUERY":
            return "list_inventory"  # Route specific queries to list too
        elif intent == "ACCEPT_QUOTE":
            return "accept_quote"
        elif state.get("error"):
            return "direct_response"
        else:
            return "direct_response"

    async def _supervisor_node(self, state: AgentState) -> dict:
        """
        Supervisor Node - Analyzes user intent and extracts parameters.

        This node uses the LLM to understand what the user wants and
        route to the appropriate workflow.
        """
        messages = state.get("messages", [])

        if not messages:
            return {
                "error": "No message provided",
                "intent": "GENERAL_QUERY",
                "next_step": "direct_response"
            }

        # Get the last user message
        last_message = messages[-1]
        user_input = last_message.content if hasattr(last_message, 'content') else str(last_message)

        # Ask LLM to classify intent
        prompt = ChatPromptTemplate.from_messages([
            ("system", SUPERVISOR_SYSTEM_PROMPT),
            ("human", "{input}")
        ])

        chain = prompt | self.llm

        try:
            response = await chain.ainvoke({"input": user_input})
            content = response.content

            # Parse JSON from response
            # Handle potential markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            parsed = json.loads(content.strip())

            return {
                "intent": parsed.get("intent", "GENERAL_QUERY"),
                "customer_name": parsed.get("customer_name"),
                "product_description": parsed.get("product_description"),
                "quantity": parsed.get("quantity"),
                "requested_date": parsed.get("requested_date"),
                "quote_selection": parsed.get("quote_selection"),
                "next_step": parsed.get("intent", "GENERAL_QUERY").lower()
            }

        except json.JSONDecodeError:
            # If LLM didn't return valid JSON, try simple intent matching
            user_lower = user_input.lower()

            if any(word in user_lower for word in ["quote", "price", "cost", "how much"]):
                return {"intent": "QUOTE_REQUEST", "next_step": "parallel_analysis"}
            elif any(word in user_lower for word in ["schedule", "reserve", "book"]):
                return {"intent": "SCHEDULE_REQUEST", "next_step": "create_job"}
            elif any(word in user_lower for word in ["status", "where is", "job"]):
                return {"intent": "JOB_STATUS", "next_step": "job_status"}
            elif any(word in user_lower for word in ["accept", "go with", "choose", "select"]) and any(word in user_lower for word in ["fastest", "cheapest", "balanced", "option"]):
                # Determine which option
                selection = None
                if "fastest" in user_lower:
                    selection = "fastest"
                elif "cheapest" in user_lower:
                    selection = "cheapest"
                elif "balanced" in user_lower:
                    selection = "balanced"
                return {"intent": "ACCEPT_QUOTE", "quote_selection": selection, "next_step": "accept_quote"}
            elif any(word in user_lower for word in ["show inventory", "list inventory", "all items", "what materials", "list materials", "show materials"]):
                return {"intent": "LIST_INVENTORY", "next_step": "list_inventory"}
            elif any(word in user_lower for word in ["inventory", "stock", "do we have"]):
                return {"intent": "INVENTORY_QUERY", "next_step": "list_inventory"}
            elif any(word in user_lower for word in ["production schedule", "show schedule", "view schedule"]):
                return {"intent": "SCHEDULE_VIEW", "next_step": "schedule_view"}
            else:
                return {"intent": "GENERAL_QUERY", "next_step": "direct_response"}

        except Exception as e:
            return {
                "error": str(e),
                "intent": "GENERAL_QUERY",
                "next_step": "direct_response"
            }

    async def _inventory_node(self, state: AgentState) -> dict:
        """
        Inventory Check Node - Part of parallel analysis.

        Checks stock levels and vendor lead times.
        """
        async with get_db_context() as db:
            inventory_service = InventoryService(db)

            # Get BOM or use demo data
            bom = state.get("bom") or [
                {"item_id": 1, "quantity": state.get("quantity", 10)},
            ]

            try:
                # Check stock for BOM items
                results = []
                for item in bom:
                    try:
                        result = await inventory_service.check_stock(
                            item_id=item["item_id"],
                            quantity_required=item["quantity"]
                        )
                        results.append(result.model_dump())
                    except ValueError:
                        # Item not found - use placeholder
                        results.append({
                            "item_id": item["item_id"],
                            "available": True,
                            "quantity_on_hand": 100,
                            "quantity_required": item["quantity"],
                            "shortage": 0,
                            "vendor_lead_time_days": 5
                        })

                # Determine overall availability
                all_available = all(r.get("available", False) for r in results)
                max_lead_time = max(
                    (r.get("vendor_lead_time_days", 0) for r in results),
                    default=7
                )

                return {
                    "inventory_data": {
                        "all_available": all_available,
                        "items_checked": results,
                        "max_lead_time_days": max_lead_time,
                        "summary": "All materials in stock" if all_available
                            else f"Some materials require {max_lead_time} days lead time"
                    }
                }

            except Exception as e:
                return {
                    "inventory_data": {
                        "error": str(e),
                        "all_available": True,
                        "max_lead_time_days": 7,
                        "summary": "Using estimated inventory data"
                    }
                }

    async def _scheduling_node(self, state: AgentState) -> dict:
        """
        Scheduling Check Node - Part of parallel analysis.

        Finds available production slots.
        """
        async with get_db_context() as db:
            scheduling_service = SchedulingService(db)

            machine_type = state.get("machine_type", "cnc")
            labor_hours = state.get("labor_hours", 8)

            try:
                result = await scheduling_service.find_slot(
                    machine_type=machine_type,
                    duration_hours=int(labor_hours)
                )

                return {
                    "schedule_data": {
                        "slot_found": True,
                        "machine_id": result.machine_id,
                        "machine_name": result.machine_name,
                        "earliest_start": result.earliest_start.isoformat(),
                        "earliest_end": result.earliest_end.isoformat(),
                        "alternatives": result.alternative_slots,
                        "summary": f"Slot available on {result.machine_name} starting {result.earliest_start.strftime('%Y-%m-%d %H:%M')}"
                    }
                }

            except ValueError as e:
                # No machines found - return placeholder
                from datetime import timedelta
                now = datetime.utcnow()
                return {
                    "schedule_data": {
                        "slot_found": True,
                        "machine_id": 1,
                        "machine_name": "CNC-Mill-1",
                        "earliest_start": (now + timedelta(days=3)).isoformat(),
                        "earliest_end": (now + timedelta(days=3, hours=8)).isoformat(),
                        "alternatives": [],
                        "summary": f"Slot available starting in 3 days"
                    }
                }

    async def _costing_node(self, state: AgentState) -> dict:
        """
        Costing Check Node - Part of parallel analysis.

        Calculates quote options: Fastest, Cheapest, Balanced.
        """
        async with get_db_context() as db:
            costing_service = CostingService(db)

            bom = state.get("bom") or [
                {"item_id": 1, "quantity": state.get("quantity", 10)},
            ]
            labor_hours = state.get("labor_hours", 8)

            # Get lead time from scheduling data
            schedule_data = state.get("schedule_data", {})
            lead_time = 7  # Default

            if schedule_data.get("earliest_start"):
                from datetime import datetime as dt
                try:
                    start = dt.fromisoformat(schedule_data["earliest_start"])
                    lead_time = (start - dt.utcnow()).days
                except:
                    pass

            try:
                options = await costing_service.calculate_quote_options(
                    bom=bom,
                    labor_hours=labor_hours,
                    current_lead_time_days=max(1, lead_time)
                )

                return {
                    "cost_data": options,
                    "quote_options": options
                }

            except Exception as e:
                # Return demo data on error
                from datetime import timedelta
                now = datetime.utcnow()
                return {
                    "cost_data": {
                        "fastest": {
                            "quote_type": "fastest",
                            "total_price": 2500.00,
                            "estimated_delivery_date": (now + timedelta(days=3)).isoformat(),
                            "lead_time_days": 3,
                            "highlights": ["Expedited delivery", "Priority scheduling"]
                        },
                        "cheapest": {
                            "quote_type": "cheapest",
                            "total_price": 1800.00,
                            "estimated_delivery_date": (now + timedelta(days=10)).isoformat(),
                            "lead_time_days": 10,
                            "highlights": ["Most economical", "Standard scheduling"]
                        },
                        "balanced": {
                            "quote_type": "balanced",
                            "total_price": 2100.00,
                            "estimated_delivery_date": (now + timedelta(days=7)).isoformat(),
                            "lead_time_days": 7,
                            "highlights": ["Recommended", "Best value"]
                        }
                    },
                    "quote_options": {
                        "error": str(e)
                    }
                }

    async def _synthesizer_node(self, state: AgentState) -> dict:
        """
        Synthesizer Node - Fan-In aggregation.

        Combines results from Inventory, Scheduling, and Costing
        to produce the final quote options response.
        """
        inventory_data = state.get("inventory_data", {})
        schedule_data = state.get("schedule_data", {})
        cost_data = state.get("cost_data", {})

        customer_name = state.get("customer_name", "Customer")
        product_description = state.get("product_description", "Custom manufacturing job")

        # Build synthesis message for LLM
        synthesis_input = f"""
Customer: {customer_name}
Product: {product_description}
Quantity: {state.get('quantity', 'Not specified')}
Requested Date: {state.get('requested_date', 'Not specified')}

INVENTORY ANALYSIS:
{json.dumps(inventory_data, indent=2, default=str)}

SCHEDULING ANALYSIS:
{json.dumps(schedule_data, indent=2, default=str)}

COSTING ANALYSIS:
{json.dumps(cost_data, indent=2, default=str)}

Please synthesize these into a clear response for the customer.
"""

        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", SYNTHESIZER_SYSTEM_PROMPT),
                ("human", "{input}")
            ])

            chain = prompt | self.llm
            response = await chain.ainvoke({"input": synthesis_input})

            return {
                "response_type": "quote_options",
                "response_data": {
                    "customer_name": customer_name,
                    "product_description": product_description,
                    "quantity": state.get("quantity"),
                    "inventory_summary": inventory_data.get("summary", ""),
                    "schedule_summary": schedule_data.get("summary", ""),
                    "options": cost_data,
                    "synthesis": response.content
                },
                "messages": [AIMessage(content=response.content)]
            }

        except Exception as e:
            # Return structured data even on LLM failure
            return {
                "response_type": "quote_options",
                "response_data": {
                    "customer_name": customer_name,
                    "options": cost_data,
                    "error": str(e)
                },
                "messages": [AIMessage(
                    content=f"I've prepared quote options for {customer_name}. "
                           f"Please review the three options: Fastest, Cheapest, and Balanced."
                )]
            }

    async def _job_status_node(self, state: AgentState) -> dict:
        """Job Status Query Node."""
        async with get_db_context() as db:
            job_service = JobService(db)

            # Try to find job
            jobs = await job_service.get_active_jobs()

            if not jobs:
                return {
                    "response_type": "job_status",
                    "response_data": {
                        "message": "No active jobs found.",
                        "jobs": []
                    },
                    "messages": [AIMessage(content="No active jobs found in the system.")]
                }

            job_list = [
                {
                    "job_number": j.job_number,
                    "customer": j.customer_name,
                    "status": j.status.value,
                    "financial_hold": j.financial_hold,
                    "created_at": j.created_at.isoformat()
                }
                for j in jobs[:10]
            ]

            return {
                "response_type": "job_status",
                "response_data": {
                    "message": f"Found {len(jobs)} active job(s).",
                    "jobs": job_list
                },
                "messages": [AIMessage(
                    content=f"Here are your {len(jobs)} active job(s). "
                           f"Use the job number to get more details."
                )]
            }

    async def _schedule_view_node(self, state: AgentState) -> dict:
        """Schedule View Node - Returns Gantt-compatible schedule data."""
        async with get_db_context() as db:
            scheduling_service = SchedulingService(db)

            schedules = await scheduling_service.get_all_schedules()

            return {
                "response_type": "schedule_view",
                "response_data": {
                    "schedules": schedules,
                    "message": "Here's the current production schedule."
                },
                "messages": [AIMessage(
                    content="Here's the current production schedule across all machines."
                )]
            }

    async def _create_job_node(self, state: AgentState) -> dict:
        """
        Create Job Node - Implements Dynamic Entry (Schedule-First).

        Creates a job in SCHEDULED status with financial hold.
        """
        async with get_db_context() as db:
            job_service = JobService(db)

            customer_name = state.get("customer_name", "Walk-in Customer")
            description = state.get("product_description", "Rush order")

            try:
                job = await job_service.create_scheduled_job(
                    customer_name=customer_name,
                    description=description,
                    financial_hold_reason="Awaiting PO"
                )

                return {
                    "response_type": "confirmation",
                    "response_data": {
                        "job_id": job.id,
                        "job_number": job.job_number,
                        "status": job.status.value,
                        "financial_hold": job.financial_hold,
                        "message": f"Job {job.job_number} created and scheduled. "
                                  f"Capacity reserved. Please provide PO to release."
                    },
                    "job_id": job.id,
                    "messages": [AIMessage(
                        content=f"Job {job.job_number} has been created and scheduled. "
                               f"Production capacity is reserved. The job is on financial hold "
                               f"pending PO confirmation. Please upload the PO to release the shipment."
                    )]
                }

            except Exception as e:
                return {
                    "response_type": "error",
                    "error": str(e),
                    "messages": [AIMessage(
                        content=f"Failed to create job: {str(e)}"
                    )]
                }

    async def _list_inventory_node(self, state: AgentState) -> dict:
        """List Inventory Node - Returns all inventory items."""
        async with get_db_context() as db:
            from sqlalchemy import select
            result = await db.execute(select(Item))
            items = list(result.scalars().all())

            if not items:
                return {
                    "response_type": "inventory_list",
                    "response_data": {
                        "message": "No inventory items found.",
                        "items": []
                    },
                    "messages": [AIMessage(
                        content="No inventory items found in the system. Use /api/seed to add demo data."
                    )]
                }

            items_list = [
                {
                    "id": item.id,
                    "name": item.name,
                    "sku": item.sku,
                    "category": item.category,
                    "quantity_on_hand": item.quantity_on_hand,
                    "cost_per_unit": float(item.cost_per_unit),
                    "reorder_point": item.reorder_point,
                    "vendor_lead_time_days": item.vendor_lead_time_days
                }
                for item in items
            ]

            # Build summary message
            summary_lines = ["**Current Inventory:**\n"]
            for item in items_list:
                status = "✅" if item["quantity_on_hand"] >= (item["reorder_point"] or 0) else "⚠️ Low"
                summary_lines.append(
                    f"- **{item['name']}** ({item['sku']}): {item['quantity_on_hand']} units @ ${item['cost_per_unit']:.2f}/ea {status}"
                )

            return {
                "response_type": "inventory_list",
                "response_data": {
                    "message": f"Found {len(items)} inventory items.",
                    "items": items_list
                },
                "messages": [AIMessage(content="\n".join(summary_lines))]
            }

    async def _accept_quote_node(self, state: AgentState) -> dict:
        """Accept Quote Node - Creates job from accepted quote option."""
        quote_selection = state.get("quote_selection")
        thread_id = state.get("thread_id")
        pending_data = state.get("pending_quote_data")

        # If no pending quote data in state, check conversation history
        if not pending_data and thread_id:
            async with get_db_context() as db:
                conv_service = ConversationService(db)
                pending_data = await conv_service.get_pending_quote(thread_id)

        if not pending_data:
            return {
                "response_type": "error",
                "response_data": {"error": "No pending quote found"},
                "messages": [AIMessage(
                    content="I don't see a pending quote to accept. Please request a quote first, then tell me which option you'd like."
                )]
            }

        if not quote_selection:
            return {
                "response_type": "clarification",
                "response_data": {"options": ["fastest", "cheapest", "balanced"]},
                "messages": [AIMessage(
                    content="Which quote option would you like to accept?\n\n"
                           "- **Fastest** - Priority production\n"
                           "- **Cheapest** - Most economical\n"
                           "- **Balanced** - Best value (recommended)"
                )]
            }

        # Get the selected quote option
        quote_options = pending_data.get("pending_quote", {})
        selected_option = quote_options.get(quote_selection.lower())

        if not selected_option:
            return {
                "response_type": "error",
                "response_data": {"error": f"Invalid option: {quote_selection}"},
                "messages": [AIMessage(
                    content=f"'{quote_selection}' is not a valid option. Please choose 'fastest', 'cheapest', or 'balanced'."
                )]
            }

        # Create the job
        async with get_db_context() as db:
            job_service = JobService(db)
            customer_name = pending_data.get("customer_name", "Customer")
            description = pending_data.get("product_description", "Custom order")

            job = await job_service.create_job(
                customer_name=customer_name,
                description=f"{description} - {quote_selection.upper()} option"
            )

            # Clear the pending quote
            if thread_id:
                conv_service = ConversationService(db)
                await conv_service.clear_pending_quote(thread_id)

            await db.commit()

            return {
                "response_type": "confirmation",
                "response_data": {
                    "job_id": job.id,
                    "job_number": job.job_number,
                    "selected_option": quote_selection,
                    "price": selected_option.get("total_price"),
                    "delivery_date": selected_option.get("estimated_delivery_date"),
                    "status": job.status.value
                },
                "job_id": job.id,
                "messages": [AIMessage(
                    content=f"**Quote Accepted!**\n\n"
                           f"Job **{job.job_number}** has been created for {customer_name}.\n\n"
                           f"- **Option:** {quote_selection.capitalize()}\n"
                           f"- **Price:** ${selected_option.get('total_price', 0):,.2f}\n"
                           f"- **Estimated Delivery:** {selected_option.get('estimated_delivery_date', 'TBD')[:10]}\n\n"
                           f"The job is now in **{job.status.value}** status."
                )]
            }

    async def _direct_response_node(self, state: AgentState) -> dict:
        """Direct Response Node - Handles general queries and errors."""
        error = state.get("error")
        intent = state.get("intent", "GENERAL_QUERY")

        if error:
            return {
                "response_type": "error",
                "response_data": {"error": error},
                "messages": [AIMessage(
                    content=f"I encountered an issue: {error}. Please try rephrasing your request."
                )]
            }

        # General help response
        return {
            "response_type": "text",
            "messages": [AIMessage(
                content="""I'm Quantum HUB, your AI manufacturing assistant. I can help you with:

- **Get a Quote**: "Quote 50 widgets for Acme Corp, need by Friday"
- **Schedule Production**: "Schedule an emergency run for Customer X"
- **Check Job Status**: "What's the status of job 20241231-0001?"
- **View Schedule**: "Show me the production schedule"
- **View Inventory**: "Show me current inventory"
- **Accept Quote**: "Accept the balanced option"

How can I help you today?"""
            )]
        }

    async def run(
        self,
        message: str,
        thread_id: str = "default",
        db: Optional[AsyncSession] = None
    ) -> dict:
        """
        Run the hub with a user message.

        Args:
            message: User's input message
            thread_id: Conversation thread ID for state persistence
            db: Optional database session for conversation history

        Returns:
            Final state with response
        """
        # Load conversation history if db provided
        conversation_history = []
        pending_quote_data = None

        if db:
            conv_service = ConversationService(db)
            conversation_history = await conv_service.get_history(thread_id, limit=10)
            pending_quote_data = await conv_service.get_pending_quote(thread_id)

        initial_state: AgentState = {
            "messages": [HumanMessage(content=message)],
            "thread_id": thread_id,
            "conversation_history": conversation_history,
            "next_step": "",
            "intent": "",
            "job_id": None,
            "customer_name": None,
            "product_description": None,
            "requested_date": None,
            "quantity": None,
            "bom": None,
            "labor_hours": 8,
            "machine_type": "cnc",
            "quote_selection": None,
            "pending_quote_data": pending_quote_data,
            "inventory_data": None,
            "schedule_data": None,
            "cost_data": None,
            "quote_options": None,
            "response_type": None,
            "response_data": None,
            "error": None
        }

        # Run the graph
        result = await self.graph.ainvoke(initial_state)

        # Store pending quote if this was a quote response
        if db and result.get("response_type") == "quote_options":
            response_data = result.get("response_data", {})
            if response_data.get("options"):
                conv_service = ConversationService(db)
                await conv_service.store_pending_quote(
                    thread_id=thread_id,
                    quote_options=response_data.get("options", {}),
                    customer_name=response_data.get("customer_name", "Customer"),
                    product_description=response_data.get("product_description", "Custom order")
                )

        return result


# Singleton instance
_hub_instance: Optional[QuantumHub] = None


def get_hub() -> QuantumHub:
    """Get or create the Quantum Hub instance."""
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = QuantumHub()
    return _hub_instance
