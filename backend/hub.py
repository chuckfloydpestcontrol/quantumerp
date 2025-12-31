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
    job_number: Optional[str]
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

    # New fields for enhanced intents
    po_number: Optional[str]
    search_query: Optional[str]
    adjustment_quantity: Optional[int]
    item_name: Optional[str]

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

You support these workflows:

**Quoting & Orders:**
- QUOTE_REQUEST: User wants a quote for manufacturing a product
- ACCEPT_QUOTE: User wants to accept a quote option (e.g., "accept the balanced option")

**Job Management:**
- SCHEDULE_REQUEST: Schedule production (Dynamic Entry - no PO required)
- JOB_STATUS: Get status overview of jobs
- GET_JOB_DETAILS: Get details of a specific job by number (e.g., "details for job 20251231-0001")
- SEARCH_JOBS: Search for jobs by customer or description
- START_JOB: Start production on a job (e.g., "start job 20251231-0001", "begin production")
- COMPLETE_JOB: Mark a job as complete (e.g., "complete job 20251231-0001", "job finished")
- CANCEL_JOB: Cancel a job (e.g., "cancel job 20251231-0001")
- ATTACH_PO: Attach PO number to release financial hold (e.g., "attach PO-12345 to job 20251231-0001")

**Inventory:**
- LIST_INVENTORY: See all inventory items
- INVENTORY_QUERY: Check specific item stock
- LOW_STOCK_ALERT: Show items below reorder point
- ADJUST_INVENTORY: Add or remove stock (e.g., "add 50 units of aluminum", "received shipment")

**Scheduling & Analytics:**
- SCHEDULE_VIEW: View production schedule
- MACHINE_UTILIZATION: Show machine usage/capacity
- FINANCIAL_HOLD_REPORT: Show jobs awaiting PO

- GENERAL_QUERY: General questions about the system

Extract these details when applicable:
- customer_name: Who is the customer
- product_description: What to manufacture
- quantity: How many units
- requested_date: When needed
- job_number: Job reference (e.g., "20251231-0001")
- material_type: Material mentioned (e.g., "aluminum 6061")
- quote_selection: Which option ("fastest", "cheapest", "balanced")
- po_number: PO number if attaching
- search_query: Search term for jobs
- new_status: Target status for job updates
- adjustment_quantity: Amount to add/remove from inventory
- item_name: Inventory item name or SKU

Respond with a JSON object:
{{
    "intent": "QUOTE_REQUEST|ACCEPT_QUOTE|SCHEDULE_REQUEST|JOB_STATUS|GET_JOB_DETAILS|SEARCH_JOBS|START_JOB|COMPLETE_JOB|CANCEL_JOB|ATTACH_PO|LIST_INVENTORY|INVENTORY_QUERY|LOW_STOCK_ALERT|ADJUST_INVENTORY|SCHEDULE_VIEW|MACHINE_UTILIZATION|FINANCIAL_HOLD_REPORT|GENERAL_QUERY",
    "customer_name": "extracted or null",
    "product_description": "what to manufacture or null",
    "quantity": "number or null",
    "requested_date": "date string or null",
    "job_number": "job number or null",
    "material_type": "material or null",
    "quote_selection": "fastest|cheapest|balanced or null",
    "po_number": "PO number or null",
    "search_query": "search term or null",
    "adjustment_quantity": "number or null",
    "item_name": "item name/SKU or null",
    "clarification_needed": "question if more info needed or null"
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

        # Add nodes - Core
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("direct_response", self._direct_response_node)

        # Add nodes - Quoting (parallel analysis)
        workflow.add_node("inventory_check", self._inventory_node)
        workflow.add_node("scheduling_check", self._scheduling_node)
        workflow.add_node("costing_check", self._costing_node)
        workflow.add_node("synthesizer", self._synthesizer_node)
        workflow.add_node("accept_quote", self._accept_quote_node)

        # Add nodes - Job Management
        workflow.add_node("job_status", self._job_status_node)
        workflow.add_node("create_job", self._create_job_node)
        workflow.add_node("get_job_details", self._get_job_details_node)
        workflow.add_node("search_jobs", self._search_jobs_node)
        workflow.add_node("update_job_status", self._update_job_status_node)
        workflow.add_node("attach_po", self._attach_po_node)

        # Add nodes - Inventory
        workflow.add_node("list_inventory", self._list_inventory_node)
        workflow.add_node("low_stock_alert", self._low_stock_alert_node)
        workflow.add_node("adjust_inventory", self._adjust_inventory_node)

        # Add nodes - Analytics
        workflow.add_node("schedule_view", self._schedule_view_node)
        workflow.add_node("machine_utilization", self._machine_utilization_node)
        workflow.add_node("financial_hold_report", self._financial_hold_report_node)

        # Set entry point
        workflow.set_entry_point("supervisor")

        # Add conditional routing from supervisor
        workflow.add_conditional_edges(
            "supervisor",
            self._route_from_supervisor,
            {
                # Quoting
                "parallel_analysis": "inventory_check",
                "accept_quote": "accept_quote",
                # Job Management
                "job_status": "job_status",
                "create_job": "create_job",
                "get_job_details": "get_job_details",
                "search_jobs": "search_jobs",
                "update_job_status": "update_job_status",
                "attach_po": "attach_po",
                # Inventory
                "list_inventory": "list_inventory",
                "low_stock_alert": "low_stock_alert",
                "adjust_inventory": "adjust_inventory",
                # Analytics
                "schedule_view": "schedule_view",
                "machine_utilization": "machine_utilization",
                "financial_hold_report": "financial_hold_report",
                # Default
                "direct_response": "direct_response",
                "end": END,
            }
        )

        # Fan-out: inventory_check leads to scheduling_check (in sequence for now)
        workflow.add_edge("inventory_check", "scheduling_check")
        workflow.add_edge("scheduling_check", "costing_check")

        # Fan-in: all analysis nodes lead to synthesizer
        workflow.add_edge("costing_check", "synthesizer")

        # Terminal nodes
        workflow.add_edge("synthesizer", END)
        workflow.add_edge("accept_quote", END)
        workflow.add_edge("job_status", END)
        workflow.add_edge("create_job", END)
        workflow.add_edge("get_job_details", END)
        workflow.add_edge("search_jobs", END)
        workflow.add_edge("update_job_status", END)
        workflow.add_edge("attach_po", END)
        workflow.add_edge("list_inventory", END)
        workflow.add_edge("low_stock_alert", END)
        workflow.add_edge("adjust_inventory", END)
        workflow.add_edge("schedule_view", END)
        workflow.add_edge("machine_utilization", END)
        workflow.add_edge("financial_hold_report", END)
        workflow.add_edge("direct_response", END)

        return workflow.compile()

    def _route_from_supervisor(self, state: AgentState) -> str:
        """Route based on supervisor's intent classification."""
        intent = state.get("intent", "").upper()

        # Quoting
        if intent == "QUOTE_REQUEST":
            return "parallel_analysis"
        elif intent == "ACCEPT_QUOTE":
            return "accept_quote"

        # Job Management
        elif intent == "SCHEDULE_REQUEST":
            return "create_job"
        elif intent == "JOB_STATUS":
            return "job_status"
        elif intent == "GET_JOB_DETAILS":
            return "get_job_details"
        elif intent == "SEARCH_JOBS":
            return "search_jobs"
        elif intent in ("START_JOB", "COMPLETE_JOB", "CANCEL_JOB"):
            return "update_job_status"
        elif intent == "ATTACH_PO":
            return "attach_po"

        # Inventory
        elif intent == "LIST_INVENTORY":
            return "list_inventory"
        elif intent == "INVENTORY_QUERY":
            return "list_inventory"
        elif intent == "LOW_STOCK_ALERT":
            return "low_stock_alert"
        elif intent == "ADJUST_INVENTORY":
            return "adjust_inventory"

        # Analytics
        elif intent == "SCHEDULE_VIEW":
            return "schedule_view"
        elif intent == "MACHINE_UTILIZATION":
            return "machine_utilization"
        elif intent == "FINANCIAL_HOLD_REPORT":
            return "financial_hold_report"

        # Error or default
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
                "job_number": parsed.get("job_number"),
                "customer_name": parsed.get("customer_name"),
                "product_description": parsed.get("product_description"),
                "quantity": parsed.get("quantity"),
                "requested_date": parsed.get("requested_date"),
                "quote_selection": parsed.get("quote_selection"),
                "po_number": parsed.get("po_number"),
                "search_query": parsed.get("search_query"),
                "adjustment_quantity": parsed.get("adjustment_quantity"),
                "item_name": parsed.get("item_name"),
                "next_step": parsed.get("intent", "GENERAL_QUERY").lower()
            }

        except json.JSONDecodeError:
            # If LLM didn't return valid JSON, try simple intent matching
            user_lower = user_input.lower()

            # Extract job number pattern (YYYYMMDD-XXXX)
            import re
            job_match = re.search(r'\d{8}-\d{4}', user_input)
            job_number = job_match.group(0) if job_match else None

            # Quoting
            if any(word in user_lower for word in ["quote", "price", "cost", "how much"]):
                return {"intent": "QUOTE_REQUEST", "next_step": "parallel_analysis"}
            elif any(word in user_lower for word in ["accept", "go with", "choose", "select"]) and any(word in user_lower for word in ["fastest", "cheapest", "balanced", "option"]):
                selection = "fastest" if "fastest" in user_lower else "cheapest" if "cheapest" in user_lower else "balanced" if "balanced" in user_lower else None
                return {"intent": "ACCEPT_QUOTE", "quote_selection": selection, "next_step": "accept_quote"}

            # Job Management
            elif any(word in user_lower for word in ["start production", "begin production", "start job"]):
                return {"intent": "START_JOB", "job_number": job_number, "next_step": "update_job_status"}
            elif any(word in user_lower for word in ["complete job", "finish job", "job complete", "mark complete"]):
                return {"intent": "COMPLETE_JOB", "job_number": job_number, "next_step": "update_job_status"}
            elif any(word in user_lower for word in ["cancel job", "cancel order"]):
                return {"intent": "CANCEL_JOB", "job_number": job_number, "next_step": "update_job_status"}
            elif "attach po" in user_lower or "po number" in user_lower or "add po" in user_lower:
                po_match = re.search(r'PO[-#]?\d+', user_input, re.IGNORECASE)
                po_number = po_match.group(0) if po_match else None
                return {"intent": "ATTACH_PO", "job_number": job_number, "po_number": po_number, "next_step": "attach_po"}
            elif any(word in user_lower for word in ["search job", "find job", "look up job", "jobs for"]):
                return {"intent": "SEARCH_JOBS", "next_step": "search_jobs"}
            elif job_number and any(word in user_lower for word in ["details", "info", "about"]):
                return {"intent": "GET_JOB_DETAILS", "job_number": job_number, "next_step": "get_job_details"}
            elif any(word in user_lower for word in ["schedule", "reserve", "book", "emergency"]):
                return {"intent": "SCHEDULE_REQUEST", "next_step": "create_job"}
            elif any(word in user_lower for word in ["status", "active jobs", "job list"]):
                return {"intent": "JOB_STATUS", "next_step": "job_status"}

            # Inventory
            elif any(word in user_lower for word in ["low stock", "reorder", "running low", "need to order"]):
                return {"intent": "LOW_STOCK_ALERT", "next_step": "low_stock_alert"}
            elif any(word in user_lower for word in ["add inventory", "received", "adjust stock", "add stock", "remove stock"]):
                return {"intent": "ADJUST_INVENTORY", "next_step": "adjust_inventory"}
            elif any(word in user_lower for word in ["show inventory", "list inventory", "all items", "list materials"]):
                return {"intent": "LIST_INVENTORY", "next_step": "list_inventory"}
            elif any(word in user_lower for word in ["inventory", "stock", "do we have"]):
                return {"intent": "INVENTORY_QUERY", "next_step": "list_inventory"}

            # Analytics
            elif any(word in user_lower for word in ["machine utilization", "machine usage", "capacity"]):
                return {"intent": "MACHINE_UTILIZATION", "next_step": "machine_utilization"}
            elif any(word in user_lower for word in ["financial hold", "awaiting po", "pending po", "needs po"]):
                return {"intent": "FINANCIAL_HOLD_REPORT", "next_step": "financial_hold_report"}
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

    # =========================================================================
    # New Node Handlers - Job Management
    # =========================================================================

    async def _get_job_details_node(self, state: AgentState) -> dict:
        """Get details for a specific job."""
        job_number = state.get("job_number")

        if not job_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which job would you like details for? Please provide the job number (e.g., 20251231-0001)."
                )]
            }

        async with get_db_context() as db:
            job_service = JobService(db)
            job = await job_service.get_job_by_number(job_number)

            if not job:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Job **{job_number}** not found.")]
                }

            details = f"""**Job Details: {job.job_number}**

- **Customer:** {job.customer_name}
- **Description:** {job.description or 'N/A'}
- **Status:** {job.status.value}
- **Priority:** {job.priority}
- **Financial Hold:** {'Yes - ' + (job.financial_hold_reason or 'Awaiting PO') if job.financial_hold else 'No'}
- **PO Number:** {job.po_number or 'Not attached'}
- **Created:** {job.created_at.strftime('%Y-%m-%d %H:%M')}
- **Estimated Delivery:** {job.estimated_delivery_date.strftime('%Y-%m-%d') if job.estimated_delivery_date else 'TBD'}"""

            return {
                "response_type": "job_details",
                "response_data": {
                    "job_number": job.job_number,
                    "customer_name": job.customer_name,
                    "status": job.status.value,
                    "financial_hold": job.financial_hold,
                    "po_number": job.po_number
                },
                "messages": [AIMessage(content=details)]
            }

    async def _search_jobs_node(self, state: AgentState) -> dict:
        """Search for jobs by customer or description."""
        search_query = state.get("search_query") or state.get("customer_name") or ""

        if not search_query:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="What would you like to search for? You can search by customer name, job number, or description."
                )]
            }

        async with get_db_context() as db:
            job_service = JobService(db)
            jobs = await job_service.search_jobs(search_query)

            if not jobs:
                return {
                    "response_type": "search_results",
                    "response_data": {"jobs": [], "query": search_query},
                    "messages": [AIMessage(content=f"No jobs found matching '{search_query}'.")]
                }

            results = [f"**Search Results for '{search_query}':**\n"]
            for job in jobs[:10]:
                status_icon = "🟢" if job.status.value in ["completed", "in_production"] else "🟡" if job.status.value == "scheduled" else "⚪"
                results.append(f"{status_icon} **{job.job_number}** - {job.customer_name} ({job.status.value})")

            return {
                "response_type": "search_results",
                "response_data": {"jobs": [{"job_number": j.job_number, "customer": j.customer_name, "status": j.status.value} for j in jobs[:10]]},
                "messages": [AIMessage(content="\n".join(results))]
            }

    async def _update_job_status_node(self, state: AgentState) -> dict:
        """Update job status (start, complete, cancel)."""
        from models import JobStatus as JS

        job_number = state.get("job_number")
        intent = state.get("intent", "").upper()

        if not job_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which job would you like to update? Please provide the job number."
                )]
            }

        # Map intent to status
        status_map = {
            "START_JOB": JS.IN_PRODUCTION,
            "COMPLETE_JOB": JS.COMPLETED,
            "CANCEL_JOB": JS.CANCELLED,
        }
        new_status = status_map.get(intent)

        if not new_status:
            return {
                "response_type": "error",
                "messages": [AIMessage(content="Invalid status update request.")]
            }

        async with get_db_context() as db:
            job_service = JobService(db)
            job = await job_service.get_job_by_number(job_number)

            if not job:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Job **{job_number}** not found.")]
                }

            old_status = job.status.value
            job = await job_service.update_job_status(job.id, new_status)
            await db.commit()

            action_word = "started" if intent == "START_JOB" else "completed" if intent == "COMPLETE_JOB" else "cancelled"

            return {
                "response_type": "confirmation",
                "response_data": {
                    "job_number": job.job_number,
                    "old_status": old_status,
                    "new_status": job.status.value
                },
                "messages": [AIMessage(
                    content=f"**Job {action_word}!**\n\nJob **{job.job_number}** has been {action_word}.\n- Previous status: {old_status}\n- New status: **{job.status.value}**"
                )]
            }

    async def _attach_po_node(self, state: AgentState) -> dict:
        """Attach PO number to a job and release financial hold."""
        job_number = state.get("job_number")
        po_number = state.get("po_number")

        if not job_number or not po_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="To attach a PO, I need both the job number and PO number.\n\nExample: 'Attach PO-12345 to job 20251231-0001'"
                )]
            }

        async with get_db_context() as db:
            job_service = JobService(db)
            job = await job_service.get_job_by_number(job_number)

            if not job:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Job **{job_number}** not found.")]
                }

            job = await job_service.attach_po(job.id, po_number)
            await db.commit()

            return {
                "response_type": "confirmation",
                "response_data": {
                    "job_number": job.job_number,
                    "po_number": po_number,
                    "financial_hold": job.financial_hold
                },
                "messages": [AIMessage(
                    content=f"**PO Attached!**\n\nPO **{po_number}** has been attached to job **{job.job_number}**.\n\n- Financial hold: **Released**\n- Job is now cleared for shipment."
                )]
            }

    # =========================================================================
    # New Node Handlers - Inventory
    # =========================================================================

    async def _low_stock_alert_node(self, state: AgentState) -> dict:
        """Show items below reorder point."""
        async with get_db_context() as db:
            inventory_service = InventoryService(db)
            low_items = await inventory_service.get_low_stock_items()

            if not low_items:
                return {
                    "response_type": "low_stock",
                    "response_data": {"items": []},
                    "messages": [AIMessage(content="**All inventory levels are healthy!** No items below reorder point.")]
                }

            lines = ["**Low Stock Alert:**\n"]
            for item in low_items:
                shortage = item.reorder_point - item.quantity_on_hand
                lines.append(
                    f"⚠️ **{item.name}** ({item.sku}): {item.quantity_on_hand} units (reorder at {item.reorder_point}, need {shortage} more)"
                )

            return {
                "response_type": "low_stock",
                "response_data": {"items": [{"name": i.name, "qty": i.quantity_on_hand, "reorder": i.reorder_point} for i in low_items]},
                "messages": [AIMessage(content="\n".join(lines))]
            }

    async def _adjust_inventory_node(self, state: AgentState) -> dict:
        """Adjust inventory quantity."""
        item_name = state.get("item_name")
        adjustment = state.get("adjustment_quantity")

        if not item_name or adjustment is None:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="To adjust inventory, please specify the item and quantity.\n\nExamples:\n- 'Add 50 units of Aluminum 6061'\n- 'Received 100 M5 screws'\n- 'Remove 10 steel bars'"
                )]
            }

        async with get_db_context() as db:
            # Find item by name or SKU
            from sqlalchemy import select
            result = await db.execute(
                select(Item).where(
                    (Item.name.ilike(f"%{item_name}%")) |
                    (Item.sku.ilike(f"%{item_name}%"))
                )
            )
            item = result.scalar_one_or_none()

            if not item:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Item '{item_name}' not found in inventory.")]
                }

            old_qty = item.quantity_on_hand
            item.quantity_on_hand += int(adjustment)
            await db.commit()

            action = "Added" if adjustment > 0 else "Removed"
            return {
                "response_type": "confirmation",
                "response_data": {
                    "item": item.name,
                    "old_qty": old_qty,
                    "adjustment": adjustment,
                    "new_qty": item.quantity_on_hand
                },
                "messages": [AIMessage(
                    content=f"**Inventory Updated!**\n\n{action} {abs(adjustment)} units of **{item.name}**.\n- Previous: {old_qty} units\n- New: **{item.quantity_on_hand} units**"
                )]
            }

    # =========================================================================
    # New Node Handlers - Analytics
    # =========================================================================

    async def _machine_utilization_node(self, state: AgentState) -> dict:
        """Show machine utilization/capacity."""
        async with get_db_context() as db:
            from sqlalchemy import select, func
            from models import Machine, ProductionSlot

            # Get machines
            result = await db.execute(select(Machine))
            machines = list(result.scalars().all())

            if not machines:
                return {
                    "response_type": "utilization",
                    "messages": [AIMessage(content="No machines configured in the system.")]
                }

            # Calculate utilization for each machine (last 7 days)
            from datetime import timedelta
            now = datetime.utcnow()
            week_ago = now - timedelta(days=7)

            lines = ["**Machine Utilization (Last 7 Days):**\n"]
            for machine in machines:
                # Count scheduled hours
                result = await db.execute(
                    select(func.count(ProductionSlot.id))
                    .where(ProductionSlot.machine_id == machine.id)
                    .where(ProductionSlot.start_time >= week_ago)
                )
                slot_count = result.scalar() or 0

                # Assuming 8-hour slots, 40 hours available per week
                utilized_hours = slot_count * 8
                utilization_pct = min(100, (utilized_hours / 40) * 100)

                bar = "█" * int(utilization_pct / 10) + "░" * (10 - int(utilization_pct / 10))
                status = "🔴 Overbooked" if utilization_pct > 100 else "🟢 Available" if utilization_pct < 80 else "🟡 Busy"

                lines.append(f"**{machine.name}** [{bar}] {utilization_pct:.0f}% {status}")
                lines.append(f"  Rate: ${machine.hourly_rate}/hr | Jobs: {slot_count}")

            return {
                "response_type": "utilization",
                "response_data": {"machines": [{"name": m.name, "rate": m.hourly_rate} for m in machines]},
                "messages": [AIMessage(content="\n".join(lines))]
            }

    async def _financial_hold_report_node(self, state: AgentState) -> dict:
        """Show jobs awaiting PO (on financial hold)."""
        async with get_db_context() as db:
            job_service = JobService(db)
            jobs = await job_service.get_jobs_on_financial_hold()

            if not jobs:
                return {
                    "response_type": "financial_hold",
                    "response_data": {"jobs": []},
                    "messages": [AIMessage(content="**No jobs on financial hold!** All jobs have POs attached.")]
                }

            lines = ["**Jobs Awaiting PO:**\n"]
            now = datetime.utcnow()
            for job in jobs:
                # Handle timezone-aware datetimes
                created = job.created_at.replace(tzinfo=None) if job.created_at.tzinfo else job.created_at
                days_waiting = (now - created).days
                urgency = "🔴" if days_waiting > 5 else "🟡" if days_waiting > 2 else "🟢"
                lines.append(
                    f"{urgency} **{job.job_number}** - {job.customer_name} ({days_waiting} days)"
                )
                lines.append(f"   Reason: {job.financial_hold_reason or 'Awaiting PO'}")

            lines.append(f"\n_Total: {len(jobs)} job(s) on hold_")

            def calc_days(j):
                created = j.created_at.replace(tzinfo=None) if j.created_at.tzinfo else j.created_at
                return (now - created).days

            return {
                "response_type": "financial_hold",
                "response_data": {"jobs": [{"job_number": j.job_number, "customer": j.customer_name, "days": calc_days(j)} for j in jobs]},
                "messages": [AIMessage(content="\n".join(lines))]
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

**Quoting:**
- "Quote 50 widgets for Acme Corp, need by Friday"
- "Accept the balanced option"

**Job Management:**
- "Schedule emergency production for Customer X"
- "Start job 20251231-0001" / "Complete job" / "Cancel job"
- "Attach PO-12345 to job 20251231-0001"
- "Search jobs for Acme" / "Details for job 20251231-0001"

**Inventory:**
- "Show inventory" / "Low stock alerts"
- "Add 50 units of aluminum"

**Analytics:**
- "Show production schedule"
- "Machine utilization"
- "Jobs awaiting PO"

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
            "job_number": None,
            "customer_name": None,
            "product_description": None,
            "requested_date": None,
            "quantity": None,
            "bom": None,
            "labor_hours": 8,
            "machine_type": "cnc",
            "quote_selection": None,
            "pending_quote_data": pending_quote_data,
            "po_number": None,
            "search_query": None,
            "adjustment_quantity": None,
            "item_name": None,
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
