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
from services.estimate import EstimateService
from models import QuoteType, Item, Customer


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
    item_sku: Optional[str]
    item_cost: Optional[float]
    item_category: Optional[str]
    customer_email: Optional[str]

    # Additional fields for new intents
    quote_number: Optional[str]
    reorder_quantity: Optional[int]
    machine_name: Optional[str]
    hourly_rate: Optional[float]
    new_priority: Optional[int]
    new_delivery_date: Optional[str]

    # Estimate fields
    estimate_id: Optional[int]
    estimate_number: Optional[str]
    rejection_reason: Optional[str]

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
- CREATE_JOB: Create a new job directly (e.g., "create job for Acme Corp - 50 steel brackets")
- SCHEDULE_REQUEST: Schedule production (Dynamic Entry - no PO required)
- JOB_STATUS: Get status overview of jobs
- GET_JOB_DETAILS: Get details of a specific job by number (e.g., "details for job 20251231-0001")
- SEARCH_JOBS: Search for jobs by customer or description
- UPDATE_JOB: Update job details (e.g., "update job priority to 1", "change delivery date")
- START_JOB: Start production on a job (e.g., "start job 20251231-0001", "begin production")
- COMPLETE_JOB: Mark a job as complete (e.g., "complete job 20251231-0001", "job finished")
- CANCEL_JOB: Cancel a job (e.g., "cancel job 20251231-0001")
- ATTACH_PO: Attach PO number to release financial hold (e.g., "attach PO-12345 to job 20251231-0001")

**Inventory:**
- LIST_INVENTORY: See all inventory items
- INVENTORY_QUERY: Check specific item stock
- LOW_STOCK_ALERT: Show items below reorder point
- ADJUST_INVENTORY: Add or remove stock (e.g., "add 50 units of aluminum", "received shipment")
- ADD_ITEM: Add new inventory item (e.g., "add new item Copper Wire, SKU CU-001, $25/unit")
- REORDER_ITEM: Trigger reorder/restock (e.g., "reorder aluminum", "restock steel bars")

**Customers:**
- ADD_CUSTOMER: Add a new customer (e.g., "add customer Acme Corp, email acme@example.com")
- LIST_CUSTOMERS: List all customers (e.g., "show customers", "list customers")

**Quoting:**
- VIEW_QUOTE: View a specific quote (e.g., "show quote Q-20251231-0001")
- LIST_QUOTES: List all quotes (e.g., "show pending quotes", "list quotes")

**Estimates:**
- CREATE_ESTIMATE: Create a new estimate for a customer (e.g., "create estimate for Acme", "new quote for Widget Corp")
- LIST_ESTIMATES: List all estimates (e.g., "show my estimates", "list quotes")
- VIEW_ESTIMATE: View a specific estimate (e.g., "show estimate E-123", "open E-20260102-0003")
- SUBMIT_ESTIMATE: Submit estimate for approval (e.g., "submit E-123 for approval")
- APPROVE_ESTIMATE: Approve a pending estimate (e.g., "approve estimate E-123")
- REJECT_ESTIMATE: Reject a pending estimate with reason (e.g., "reject E-123 because pricing too low")
- SEND_ESTIMATE: Send estimate to customer (e.g., "send E-123 to customer")
- ACCEPT_ESTIMATE: Mark estimate as accepted by customer (e.g., "customer accepted E-123")

**Scheduling & Analytics:**
- SCHEDULE_VIEW: View production schedule
- LIST_MACHINES: List all machines (e.g., "show machines", "list equipment")
- ADD_MACHINE: Add a new machine (e.g., "add machine CNC-Mill-3, type cnc, $80/hour")
- MACHINE_UTILIZATION: Show machine usage/capacity
- FINANCIAL_HOLD_REPORT: Show jobs awaiting PO

- GENERAL_QUERY: General questions about the system
- HELP: User wants help or wants to know what commands are available (e.g., "help", "what can you do?", "commands")

Extract these details when applicable:
- customer_name: Who is the customer
- customer_email: Customer email address
- product_description: What to manufacture
- quantity: How many units
- requested_date: When needed
- job_number: Job reference (e.g., "20251231-0001")
- material_type: Material mentioned (e.g., "aluminum 6061")
- quote_selection: Which option ("fastest", "cheapest", "balanced")
- quote_number: Quote reference (e.g., "Q-20251231-0001")
- po_number: PO number if attaching
- search_query: Search term for jobs
- adjustment_quantity: Amount to add/remove from inventory
- item_name: Inventory item name
- item_sku: Item SKU/part number
- item_cost: Cost per unit
- item_category: Item category (raw_material, hardware, consumable)
- reorder_quantity: Quantity to reorder
- machine_name: Machine name
- machine_type: Machine type (cnc, lathe, etc.)
- hourly_rate: Machine hourly rate
- new_priority: New priority value (1-10)
- new_delivery_date: New delivery date
- estimate_number: Estimate reference (e.g., "E-20260102-0001")
- rejection_reason: Reason for rejecting an estimate

Respond with a JSON object:
{{
    "intent": "QUOTE_REQUEST|ACCEPT_QUOTE|CREATE_JOB|SCHEDULE_REQUEST|JOB_STATUS|GET_JOB_DETAILS|SEARCH_JOBS|UPDATE_JOB|START_JOB|COMPLETE_JOB|CANCEL_JOB|ATTACH_PO|LIST_INVENTORY|INVENTORY_QUERY|LOW_STOCK_ALERT|ADJUST_INVENTORY|ADD_ITEM|REORDER_ITEM|ADD_CUSTOMER|LIST_CUSTOMERS|VIEW_QUOTE|LIST_QUOTES|CREATE_ESTIMATE|LIST_ESTIMATES|VIEW_ESTIMATE|SUBMIT_ESTIMATE|APPROVE_ESTIMATE|REJECT_ESTIMATE|SEND_ESTIMATE|ACCEPT_ESTIMATE|SCHEDULE_VIEW|LIST_MACHINES|ADD_MACHINE|MACHINE_UTILIZATION|FINANCIAL_HOLD_REPORT|GENERAL_QUERY|HELP",
    "customer_name": "extracted or null",
    "customer_email": "email or null",
    "product_description": "what to manufacture or null",
    "quantity": "number or null",
    "requested_date": "date string or null",
    "job_number": "job number or null",
    "material_type": "material or null",
    "quote_selection": "fastest|cheapest|balanced or null",
    "quote_number": "quote number or null",
    "po_number": "PO number or null",
    "search_query": "search term or null",
    "adjustment_quantity": "number or null",
    "item_name": "item name or null",
    "item_sku": "SKU or null",
    "item_cost": "cost per unit or null",
    "item_category": "category or null",
    "reorder_quantity": "quantity or null",
    "machine_name": "machine name or null",
    "machine_type": "machine type or null",
    "hourly_rate": "rate or null",
    "new_priority": "priority 1-10 or null",
    "new_delivery_date": "date string or null",
    "estimate_number": "estimate number or null",
    "rejection_reason": "reason for rejection or null",
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
        workflow.add_node("create_job_direct", self._create_job_direct_node)
        workflow.add_node("get_job_details", self._get_job_details_node)
        workflow.add_node("search_jobs", self._search_jobs_node)
        workflow.add_node("update_job", self._update_job_node)
        workflow.add_node("update_job_status", self._update_job_status_node)
        workflow.add_node("attach_po", self._attach_po_node)

        # Add nodes - Inventory
        workflow.add_node("list_inventory", self._list_inventory_node)
        workflow.add_node("low_stock_alert", self._low_stock_alert_node)
        workflow.add_node("adjust_inventory", self._adjust_inventory_node)
        workflow.add_node("add_item", self._add_item_node)
        workflow.add_node("reorder_item", self._reorder_item_node)

        # Add nodes - Customer
        workflow.add_node("add_customer", self._add_customer_node)
        workflow.add_node("list_customers", self._list_customers_node)

        # Add nodes - Quoting (view/list)
        workflow.add_node("view_quote", self._view_quote_node)
        workflow.add_node("list_quotes", self._list_quotes_node)

        # Add nodes - Estimates
        workflow.add_node("create_estimate", self._create_estimate_node)
        workflow.add_node("list_estimates", self._list_estimates_node)
        workflow.add_node("view_estimate", self._view_estimate_node)
        workflow.add_node("submit_estimate", self._submit_estimate_node)
        workflow.add_node("approve_estimate", self._approve_estimate_node)
        workflow.add_node("reject_estimate", self._reject_estimate_node)
        workflow.add_node("send_estimate", self._send_estimate_node)
        workflow.add_node("accept_estimate", self._accept_estimate_node)

        # Add nodes - Analytics/Machines
        workflow.add_node("schedule_view", self._schedule_view_node)
        workflow.add_node("list_machines", self._list_machines_node)
        workflow.add_node("add_machine", self._add_machine_node)
        workflow.add_node("machine_utilization", self._machine_utilization_node)
        workflow.add_node("financial_hold_report", self._financial_hold_report_node)

        # Add node - Help
        workflow.add_node("help", self._help_node)

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
                "view_quote": "view_quote",
                "list_quotes": "list_quotes",
                # Estimates
                "create_estimate": "create_estimate",
                "list_estimates": "list_estimates",
                "view_estimate": "view_estimate",
                "submit_estimate": "submit_estimate",
                "approve_estimate": "approve_estimate",
                "reject_estimate": "reject_estimate",
                "send_estimate": "send_estimate",
                "accept_estimate": "accept_estimate",
                # Job Management
                "job_status": "job_status",
                "create_job": "create_job",
                "create_job_direct": "create_job_direct",
                "get_job_details": "get_job_details",
                "search_jobs": "search_jobs",
                "update_job": "update_job",
                "update_job_status": "update_job_status",
                "attach_po": "attach_po",
                # Inventory
                "list_inventory": "list_inventory",
                "low_stock_alert": "low_stock_alert",
                "adjust_inventory": "adjust_inventory",
                "add_item": "add_item",
                "reorder_item": "reorder_item",
                # Customer
                "add_customer": "add_customer",
                "list_customers": "list_customers",
                # Machines/Analytics
                "schedule_view": "schedule_view",
                "list_machines": "list_machines",
                "add_machine": "add_machine",
                "machine_utilization": "machine_utilization",
                "financial_hold_report": "financial_hold_report",
                "help": "help",
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
        workflow.add_edge("view_quote", END)
        workflow.add_edge("list_quotes", END)
        workflow.add_edge("create_estimate", END)
        workflow.add_edge("list_estimates", END)
        workflow.add_edge("view_estimate", END)
        workflow.add_edge("submit_estimate", END)
        workflow.add_edge("approve_estimate", END)
        workflow.add_edge("reject_estimate", END)
        workflow.add_edge("send_estimate", END)
        workflow.add_edge("accept_estimate", END)
        workflow.add_edge("job_status", END)
        workflow.add_edge("create_job", END)
        workflow.add_edge("create_job_direct", END)
        workflow.add_edge("get_job_details", END)
        workflow.add_edge("search_jobs", END)
        workflow.add_edge("update_job", END)
        workflow.add_edge("update_job_status", END)
        workflow.add_edge("attach_po", END)
        workflow.add_edge("list_inventory", END)
        workflow.add_edge("low_stock_alert", END)
        workflow.add_edge("adjust_inventory", END)
        workflow.add_edge("add_item", END)
        workflow.add_edge("reorder_item", END)
        workflow.add_edge("add_customer", END)
        workflow.add_edge("list_customers", END)
        workflow.add_edge("schedule_view", END)
        workflow.add_edge("list_machines", END)
        workflow.add_edge("add_machine", END)
        workflow.add_edge("machine_utilization", END)
        workflow.add_edge("financial_hold_report", END)
        workflow.add_edge("help", END)
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
        elif intent == "VIEW_QUOTE":
            return "view_quote"
        elif intent == "LIST_QUOTES":
            return "list_quotes"

        # Estimates
        elif intent == "CREATE_ESTIMATE":
            return "create_estimate"
        elif intent == "LIST_ESTIMATES":
            return "list_estimates"
        elif intent == "VIEW_ESTIMATE":
            return "view_estimate"
        elif intent == "SUBMIT_ESTIMATE":
            return "submit_estimate"
        elif intent == "APPROVE_ESTIMATE":
            return "approve_estimate"
        elif intent == "REJECT_ESTIMATE":
            return "reject_estimate"
        elif intent == "SEND_ESTIMATE":
            return "send_estimate"
        elif intent == "ACCEPT_ESTIMATE":
            return "accept_estimate"

        # Job Management
        elif intent == "SCHEDULE_REQUEST":
            return "create_job"
        elif intent == "JOB_STATUS":
            return "job_status"
        elif intent == "GET_JOB_DETAILS":
            return "get_job_details"
        elif intent == "SEARCH_JOBS":
            return "search_jobs"
        elif intent == "UPDATE_JOB":
            return "update_job"
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
        elif intent == "ADD_ITEM":
            return "add_item"
        elif intent == "REORDER_ITEM":
            return "reorder_item"

        # Customer
        elif intent == "ADD_CUSTOMER":
            return "add_customer"
        elif intent == "LIST_CUSTOMERS":
            return "list_customers"

        # Job - Direct creation
        elif intent == "CREATE_JOB":
            return "create_job_direct"

        # Machines
        elif intent == "LIST_MACHINES":
            return "list_machines"
        elif intent == "ADD_MACHINE":
            return "add_machine"

        # Analytics
        elif intent == "SCHEDULE_VIEW":
            return "schedule_view"
        elif intent == "MACHINE_UTILIZATION":
            return "machine_utilization"
        elif intent == "FINANCIAL_HOLD_REPORT":
            return "financial_hold_report"

        # Help
        elif intent == "HELP":
            return "help"

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
                "customer_email": parsed.get("customer_email"),
                "product_description": parsed.get("product_description"),
                "quantity": parsed.get("quantity"),
                "requested_date": parsed.get("requested_date"),
                "quote_selection": parsed.get("quote_selection"),
                "quote_number": parsed.get("quote_number"),
                "po_number": parsed.get("po_number"),
                "search_query": parsed.get("search_query"),
                "adjustment_quantity": parsed.get("adjustment_quantity"),
                "item_name": parsed.get("item_name"),
                "item_sku": parsed.get("item_sku"),
                "item_cost": parsed.get("item_cost"),
                "item_category": parsed.get("item_category"),
                "reorder_quantity": parsed.get("reorder_quantity"),
                "machine_name": parsed.get("machine_name"),
                "machine_type": parsed.get("machine_type"),
                "hourly_rate": parsed.get("hourly_rate"),
                "new_priority": parsed.get("new_priority"),
                "new_delivery_date": parsed.get("new_delivery_date"),
                "estimate_number": parsed.get("estimate_number"),
                "rejection_reason": parsed.get("rejection_reason"),
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
            elif any(word in user_lower for word in ["add new item", "new item", "create item", "add item"]) and not any(word in user_lower for word in ["add inventory", "adjust"]):
                return {"intent": "ADD_ITEM", "next_step": "add_item"}
            elif any(word in user_lower for word in ["add inventory", "received", "adjust stock", "add stock", "remove stock"]):
                return {"intent": "ADJUST_INVENTORY", "next_step": "adjust_inventory"}
            elif any(word in user_lower for word in ["show inventory", "list inventory", "all items", "list materials"]):
                return {"intent": "LIST_INVENTORY", "next_step": "list_inventory"}
            elif any(word in user_lower for word in ["inventory", "stock", "do we have"]):
                return {"intent": "INVENTORY_QUERY", "next_step": "list_inventory"}

            # Customer
            elif any(word in user_lower for word in ["add customer", "new customer", "create customer"]):
                return {"intent": "ADD_CUSTOMER", "next_step": "add_customer"}
            elif any(word in user_lower for word in ["list customers", "show customers", "all customers"]):
                return {"intent": "LIST_CUSTOMERS", "next_step": "list_customers"}

            # Direct job creation (without quote)
            elif any(word in user_lower for word in ["create job", "new job", "add job"]) and "quote" not in user_lower:
                return {"intent": "CREATE_JOB", "next_step": "create_job_direct"}

            # Job update
            elif any(word in user_lower for word in ["update job", "change job", "modify job", "change priority", "update priority"]):
                return {"intent": "UPDATE_JOB", "job_number": job_number, "next_step": "update_job"}

            # Quoting - view/list
            elif any(word in user_lower for word in ["view quote", "show quote", "quote details"]):
                return {"intent": "VIEW_QUOTE", "next_step": "view_quote"}
            elif any(word in user_lower for word in ["list quotes", "show quotes", "all quotes", "pending quotes"]):
                return {"intent": "LIST_QUOTES", "next_step": "list_quotes"}

            # Estimates
            elif any(word in user_lower for word in ["create estimate", "new estimate", "make estimate", "new quote for"]):
                return {"intent": "CREATE_ESTIMATE", "next_step": "create_estimate"}
            elif any(word in user_lower for word in ["list estimates", "show estimates", "my estimates", "all estimates"]):
                return {"intent": "LIST_ESTIMATES", "next_step": "list_estimates"}
            elif re.search(r'(show|view|open)\s*(estimate|e-)\s*', user_lower):
                estimate_match = re.search(r'E-\d{8}-\d{4}', user_input, re.IGNORECASE)
                return {"intent": "VIEW_ESTIMATE", "estimate_number": estimate_match.group(0) if estimate_match else None, "next_step": "view_estimate"}
            elif any(word in user_lower for word in ["submit estimate", "submit e-"]):
                estimate_match = re.search(r'E-\d{8}-\d{4}', user_input, re.IGNORECASE)
                return {"intent": "SUBMIT_ESTIMATE", "estimate_number": estimate_match.group(0) if estimate_match else None, "next_step": "submit_estimate"}
            elif any(word in user_lower for word in ["approve estimate", "approve e-"]):
                estimate_match = re.search(r'E-\d{8}-\d{4}', user_input, re.IGNORECASE)
                return {"intent": "APPROVE_ESTIMATE", "estimate_number": estimate_match.group(0) if estimate_match else None, "next_step": "approve_estimate"}
            elif any(word in user_lower for word in ["reject estimate", "reject e-"]):
                estimate_match = re.search(r'E-\d{8}-\d{4}', user_input, re.IGNORECASE)
                return {"intent": "REJECT_ESTIMATE", "estimate_number": estimate_match.group(0) if estimate_match else None, "next_step": "reject_estimate"}
            elif any(word in user_lower for word in ["send estimate", "send e-"]):
                estimate_match = re.search(r'E-\d{8}-\d{4}', user_input, re.IGNORECASE)
                return {"intent": "SEND_ESTIMATE", "estimate_number": estimate_match.group(0) if estimate_match else None, "next_step": "send_estimate"}
            elif any(word in user_lower for word in ["customer accepted", "accepted estimate", "accepted e-"]):
                estimate_match = re.search(r'E-\d{8}-\d{4}', user_input, re.IGNORECASE)
                return {"intent": "ACCEPT_ESTIMATE", "estimate_number": estimate_match.group(0) if estimate_match else None, "next_step": "accept_estimate"}

            # Reorder
            elif any(word in user_lower for word in ["reorder", "restock"]) and "point" not in user_lower:
                return {"intent": "REORDER_ITEM", "next_step": "reorder_item"}

            # Machines
            elif any(word in user_lower for word in ["list machines", "show machines", "all machines", "equipment list"]):
                return {"intent": "LIST_MACHINES", "next_step": "list_machines"}
            elif any(word in user_lower for word in ["add machine", "new machine", "create machine"]):
                return {"intent": "ADD_MACHINE", "next_step": "add_machine"}

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

    async def _create_job_direct_node(self, state: AgentState) -> dict:
        """Create a job directly without going through quote workflow."""
        customer_name = state.get("customer_name")
        description = state.get("product_description")
        quantity = state.get("quantity")

        if not customer_name or not description:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="To create a job, I need at least the customer name and what to produce.\n\n"
                           "Example: 'Create job for Acme Corp - 50 steel brackets'"
                )]
            }

        async with get_db_context() as db:
            job_service = JobService(db)

            # Build full description with quantity if provided
            full_description = f"{description}"
            if quantity:
                full_description = f"{quantity}x {description}"

            job = await job_service.create_job(
                customer_name=customer_name,
                description=full_description
            )

            return {
                "response_type": "confirmation",
                "response_data": {
                    "job_id": job.id,
                    "job_number": job.job_number,
                    "customer_name": customer_name,
                    "description": full_description,
                    "status": job.status.value
                },
                "job_id": job.id,
                "messages": [AIMessage(
                    content=f"**Job Created!**\n\n"
                           f"Job **{job.job_number}** has been created.\n\n"
                           f"- **Customer:** {customer_name}\n"
                           f"- **Description:** {full_description}\n"
                           f"- **Status:** {job.status.value}\n\n"
                           f"You can now start production or attach a PO to this job."
                )]
            }

    async def _add_item_node(self, state: AgentState) -> dict:
        """Add a new inventory item."""
        item_name = state.get("item_name")
        item_sku = state.get("item_sku")
        item_cost = state.get("item_cost")
        item_category = state.get("item_category", "raw_material")
        quantity = state.get("quantity") or state.get("adjustment_quantity") or 0

        if not item_name:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="To add a new inventory item, I need at least the item name.\n\n"
                           "Example: 'Add new item Copper Wire, SKU CU-001, $25/unit, category raw_material'"
                )]
            }

        async with get_db_context() as db:
            from sqlalchemy import select

            # Check if item already exists
            if item_sku:
                result = await db.execute(select(Item).where(Item.sku == item_sku))
                existing = result.scalar_one_or_none()
                if existing:
                    return {
                        "response_type": "error",
                        "messages": [AIMessage(
                            content=f"An item with SKU **{item_sku}** already exists: {existing.name}"
                        )]
                    }

            # Generate SKU if not provided
            if not item_sku:
                # Simple SKU generation: first 3 letters uppercase + counter
                prefix = ''.join(c for c in item_name.upper() if c.isalpha())[:3]
                result = await db.execute(select(Item).where(Item.sku.like(f"{prefix}-%")))
                count = len(list(result.scalars().all()))
                item_sku = f"{prefix}-{count + 1:03d}"

            # Create the item
            new_item = Item(
                name=item_name,
                sku=item_sku,
                category=item_category,
                quantity_on_hand=int(quantity),
                cost_per_unit=float(item_cost) if item_cost else 0.0,
                reorder_point=10,  # Default reorder point
                vendor_lead_time_days=7  # Default lead time
            )
            db.add(new_item)
            await db.commit()
            await db.refresh(new_item)

            return {
                "response_type": "confirmation",
                "response_data": {
                    "item_id": new_item.id,
                    "name": new_item.name,
                    "sku": new_item.sku,
                    "category": new_item.category,
                    "quantity": new_item.quantity_on_hand,
                    "cost": float(new_item.cost_per_unit)
                },
                "messages": [AIMessage(
                    content=f"**Item Added!**\n\n"
                           f"- **Name:** {new_item.name}\n"
                           f"- **SKU:** {new_item.sku}\n"
                           f"- **Category:** {new_item.category}\n"
                           f"- **Quantity:** {new_item.quantity_on_hand} units\n"
                           f"- **Cost:** ${float(new_item.cost_per_unit):.2f}/unit"
                )]
            }

    async def _add_customer_node(self, state: AgentState) -> dict:
        """Add a new customer."""
        customer_name = state.get("customer_name")
        customer_email = state.get("customer_email")

        if not customer_name:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="To add a new customer, I need at least the customer name.\n\n"
                           "Example: 'Add customer Acme Corp, email acme@example.com'"
                )]
            }

        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Customer

            # Check if customer already exists
            result = await db.execute(
                select(Customer).where(Customer.name.ilike(customer_name))
            )
            existing = result.scalar_one_or_none()
            if existing:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(
                        content=f"Customer **{customer_name}** already exists (ID: {existing.id})."
                    )]
                }

            # Create the customer
            new_customer = Customer(
                name=customer_name,
                email=customer_email,
                active=True
            )
            db.add(new_customer)
            await db.commit()
            await db.refresh(new_customer)

            return {
                "response_type": "confirmation",
                "response_data": {
                    "customer_id": new_customer.id,
                    "name": new_customer.name,
                    "email": new_customer.email
                },
                "messages": [AIMessage(
                    content=f"**Customer Added!**\n\n"
                           f"- **Name:** {new_customer.name}\n"
                           f"- **Email:** {new_customer.email or 'Not provided'}\n"
                           f"- **ID:** {new_customer.id}\n\n"
                           f"You can now create jobs for this customer."
                )]
            }

    async def _list_customers_node(self, state: AgentState) -> dict:
        """List all customers."""
        async with get_db_context() as db:
            from services.customer import CustomerService
            customer_service = CustomerService(db)
            customers = await customer_service.list_customers(active_only=False)

            if not customers:
                return {
                    "response_type": "customer_list",
                    "response_data": {"customers": []},
                    "messages": [AIMessage(content="No customers found in the system.")]
                }

            lines = ["**Customer List:**\n"]
            for c in customers:
                status = "Active" if c.active else "Inactive"
                email_info = f" ({c.email})" if c.email else ""
                lines.append(f"- **{c.name}**{email_info} - {status}")

            lines.append(f"\n_Total: {len(customers)} customer(s)_")

            return {
                "response_type": "customer_list",
                "response_data": {
                    "customers": [
                        {"id": c.id, "name": c.name, "email": c.email, "active": c.active}
                        for c in customers
                    ]
                },
                "messages": [AIMessage(content="\n".join(lines))]
            }

    async def _list_machines_node(self, state: AgentState) -> dict:
        """List all machines."""
        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Machine

            result = await db.execute(select(Machine).order_by(Machine.name))
            machines = list(result.scalars().all())

            if not machines:
                return {
                    "response_type": "machine_list",
                    "response_data": {"machines": []},
                    "messages": [AIMessage(content="No machines configured in the system.")]
                }

            lines = ["**Machine List:**\n"]
            for m in machines:
                status_icon = "🟢" if m.status == "operational" else "🔴"
                lines.append(f"{status_icon} **{m.name}** ({m.machine_type}) - ${m.hourly_rate:.2f}/hr")

            lines.append(f"\n_Total: {len(machines)} machine(s)_")

            return {
                "response_type": "machine_list",
                "response_data": {
                    "machines": [
                        {"id": m.id, "name": m.name, "type": m.machine_type, "rate": m.hourly_rate, "status": m.status}
                        for m in machines
                    ]
                },
                "messages": [AIMessage(content="\n".join(lines))]
            }

    async def _add_machine_node(self, state: AgentState) -> dict:
        """Add a new machine."""
        machine_name = state.get("machine_name")
        machine_type = state.get("machine_type")
        hourly_rate = state.get("hourly_rate")

        if not machine_name or not machine_type:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="To add a machine, I need the name and type.\n\n"
                           "Example: 'Add machine CNC-Mill-3, type cnc, $80/hour'"
                )]
            }

        async with get_db_context() as db:
            from models import Machine

            machine = Machine(
                name=machine_name,
                machine_type=machine_type,
                hourly_rate=float(hourly_rate or 75.0),
                status="operational"
            )
            db.add(machine)
            await db.commit()
            await db.refresh(machine)

            return {
                "response_type": "confirmation",
                "response_data": {
                    "machine_id": machine.id,
                    "name": machine.name,
                    "type": machine.machine_type,
                    "rate": machine.hourly_rate
                },
                "messages": [AIMessage(
                    content=f"**Machine Added!**\n\n"
                           f"- **Name:** {machine.name}\n"
                           f"- **Type:** {machine.machine_type}\n"
                           f"- **Rate:** ${machine.hourly_rate:.2f}/hr\n"
                           f"- **Status:** {machine.status}"
                )]
            }

    async def _update_job_node(self, state: AgentState) -> dict:
        """Update job details (priority, dates, etc.)."""
        job_number = state.get("job_number")
        new_priority = state.get("new_priority")
        new_delivery_date = state.get("new_delivery_date")

        if not job_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which job would you like to update? Please provide the job number.\n\n"
                           "Example: 'Update job 20251231-0001 priority to 1'"
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

            changes = []
            if new_priority is not None:
                old_priority = job.priority
                job.priority = int(new_priority)
                changes.append(f"Priority: {old_priority} → {new_priority}")

            if new_delivery_date:
                from datetime import datetime as dt
                try:
                    job.requested_delivery_date = dt.fromisoformat(new_delivery_date.replace('Z', '+00:00'))
                    changes.append(f"Delivery date: {new_delivery_date}")
                except ValueError:
                    changes.append(f"Delivery date: Could not parse '{new_delivery_date}'")

            if not changes:
                return {
                    "response_type": "clarification",
                    "messages": [AIMessage(
                        content="What would you like to update? You can change:\n"
                               "- Priority (1-10, where 1 is highest)\n"
                               "- Delivery date"
                    )]
                }

            await db.commit()

            return {
                "response_type": "confirmation",
                "response_data": {
                    "job_number": job.job_number,
                    "changes": changes
                },
                "messages": [AIMessage(
                    content=f"**Job Updated!**\n\nJob **{job_number}** updated:\n- " + "\n- ".join(changes)
                )]
            }

    async def _view_quote_node(self, state: AgentState) -> dict:
        """View a specific quote."""
        quote_number = state.get("quote_number")
        job_number = state.get("job_number")

        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Quote

            if quote_number:
                result = await db.execute(
                    select(Quote).where(Quote.quote_number == quote_number)
                )
            elif job_number:
                result = await db.execute(
                    select(Quote).where(Quote.quote_number.like(f"Q-{job_number}%"))
                )
            else:
                return {
                    "response_type": "clarification",
                    "messages": [AIMessage(
                        content="Please specify a quote or job number.\n\n"
                               "Example: 'View quote Q-20251231-0001' or 'Show quote for job 20251231-0001'"
                    )]
                }

            quote = result.scalar_one_or_none()
            if not quote:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content="Quote not found.")]
                }

            expired = quote.expires_at and datetime.utcnow() > quote.expires_at
            status = "EXPIRED" if expired else ("ACCEPTED" if quote.is_accepted else "PENDING")

            expires_str = quote.expires_at.strftime('%Y-%m-%d') if quote.expires_at else 'N/A'

            details = f"""**Quote Details: {quote.quote_number}**

- **Type:** {quote.quote_type.value}
- **Total Price:** ${quote.total_price:,.2f}
- **Status:** {status}
- **Material Cost:** ${quote.material_cost:,.2f}
- **Labor Cost:** ${quote.labor_cost:,.2f}
- **Overhead Cost:** ${quote.overhead_cost:,.2f}
- **Margin:** {quote.margin_percentage * 100:.0f}%
- **Lead Time:** {quote.lead_time_days or 'N/A'} days
- **Expires:** {expires_str}"""

            return {
                "response_type": "quote_details",
                "response_data": {
                    "quote_number": quote.quote_number,
                    "total": quote.total_price,
                    "status": status,
                    "type": quote.quote_type.value
                },
                "messages": [AIMessage(content=details)]
            }

    async def _list_quotes_node(self, state: AgentState) -> dict:
        """List all quotes."""
        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Quote

            result = await db.execute(
                select(Quote).order_by(Quote.created_at.desc()).limit(20)
            )
            quotes = list(result.scalars().all())

            if not quotes:
                return {
                    "response_type": "quote_list",
                    "response_data": {"quotes": []},
                    "messages": [AIMessage(content="No quotes found in the system.")]
                }

            lines = ["**Recent Quotes:**\n"]
            for q in quotes:
                expired = q.expires_at and datetime.utcnow() > q.expires_at
                status = "Expired" if expired else ("Accepted" if q.is_accepted else "Pending")
                status_icon = "🔴" if expired else ("🟢" if q.is_accepted else "🟡")
                lines.append(
                    f"{status_icon} **{q.quote_number}** - ${q.total_price:,.2f} ({q.quote_type.value}) - {status}"
                )

            lines.append(f"\n_Showing {len(quotes)} most recent quote(s)_")

            return {
                "response_type": "quote_list",
                "response_data": {
                    "quotes": [
                        {"number": q.quote_number, "price": q.total_price, "type": q.quote_type.value, "accepted": q.is_accepted}
                        for q in quotes
                    ]
                },
                "messages": [AIMessage(content="\n".join(lines))]
            }

    async def _reorder_item_node(self, state: AgentState) -> dict:
        """Trigger reorder/restock for an item."""
        item_name = state.get("item_name")
        reorder_quantity = state.get("reorder_quantity")

        if not item_name:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which item would you like to reorder?\n\n"
                           "Example: 'Reorder aluminum' or 'Restock steel bars, 100 units'"
                )]
            }

        async with get_db_context() as db:
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

            # Default quantity is 2x reorder point
            qty = reorder_quantity or (item.reorder_point * 2)

            return {
                "response_type": "confirmation",
                "response_data": {
                    "item_id": item.id,
                    "item_name": item.name,
                    "sku": item.sku,
                    "quantity": qty,
                    "vendor": item.vendor_name,
                    "lead_time_days": item.vendor_lead_time_days
                },
                "messages": [AIMessage(
                    content=f"**Reorder Initiated!**\n\n"
                           f"- **Item:** {item.name} ({item.sku})\n"
                           f"- **Quantity:** {qty} units\n"
                           f"- **Vendor:** {item.vendor_name or 'Not specified'}\n"
                           f"- **Lead Time:** {item.vendor_lead_time_days} days\n"
                           f"- **Est. Cost:** ${qty * item.cost_per_unit:,.2f}\n\n"
                           f"_Note: Full PO generation is coming in a future update._"
                )]
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

    # =========================================================================
    # Estimate Node Handlers
    # =========================================================================

    async def _create_estimate_node(self, state: AgentState) -> dict:
        """Create a new estimate for a customer."""
        customer_name = state.get("customer_name")

        if not customer_name:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="To create an estimate, I need the customer name.\n\n"
                           "Example: 'Create estimate for Acme Corp'"
                )]
            }

        async with get_db_context() as db:
            from sqlalchemy import select

            # Find customer
            result = await db.execute(
                select(Customer).where(Customer.name.ilike(f"%{customer_name}%"))
            )
            customer = result.scalar_one_or_none()

            if not customer:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(
                        content=f"Customer '{customer_name}' not found. Please add them first with 'add customer {customer_name}'"
                    )]
                }

            # Create the estimate
            estimate_service = EstimateService(db)
            estimate = await estimate_service.create_estimate(
                customer_id=customer.id,
                notes=state.get("product_description")
            )
            await db.commit()

            # Reload with relationships
            estimate = await estimate_service.get_estimate(estimate.id)

            return {
                "response_type": "estimate_card",
                "response_data": {
                    "estimate": {
                        "id": estimate.id,
                        "estimate_number": estimate.estimate_number,
                        "version": estimate.version,
                        "customer_id": estimate.customer_id,
                        "customer_name": customer.name,
                        "status": estimate.status.value,
                        "currency_code": estimate.currency_code,
                        "valid_until": estimate.valid_until.isoformat() if estimate.valid_until else None,
                        "subtotal": float(estimate.subtotal or 0),
                        "tax_amount": float(estimate.tax_amount or 0),
                        "total_amount": float(estimate.total_amount or 0),
                        "delivery_feasible": estimate.delivery_feasible,
                        "created_at": estimate.created_at.isoformat(),
                        "updated_at": estimate.updated_at.isoformat(),
                        "line_items": []
                    },
                    "message": f"Created estimate {estimate.estimate_number} for {customer.name}"
                },
                "messages": [AIMessage(
                    content=f"**Estimate Created!**\n\n"
                           f"Estimate **{estimate.estimate_number}** has been created for {customer.name}.\n\n"
                           f"Add line items using the Add Line button or say 'add item to estimate'."
                )]
            }

    async def _list_estimates_node(self, state: AgentState) -> dict:
        """List all estimates."""
        async with get_db_context() as db:
            estimate_service = EstimateService(db)
            estimates = await estimate_service.list_estimates(limit=20)

            if not estimates:
                return {
                    "response_type": "estimate_list",
                    "response_data": {"estimates": [], "message": "No estimates found."},
                    "messages": [AIMessage(content="No estimates found. Create one by saying 'create estimate for [customer name]'")]
                }

            estimate_list = []
            for est in estimates:
                customer_name = est.customer.name if est.customer else f"Customer #{est.customer_id}"
                estimate_list.append({
                    "id": est.id,
                    "estimate_number": est.estimate_number,
                    "version": est.version,
                    "customer_id": est.customer_id,
                    "customer_name": customer_name,
                    "status": est.status.value,
                    "total_amount": float(est.total_amount or 0),
                    "valid_until": est.valid_until.isoformat() if est.valid_until else None,
                    "created_at": est.created_at.isoformat()
                })

            return {
                "response_type": "estimate_list",
                "response_data": {
                    "estimates": estimate_list,
                    "message": f"Found {len(estimates)} estimate(s)"
                },
                "messages": [AIMessage(
                    content=f"Here are your {len(estimates)} estimate(s). Click on one to view details."
                )]
            }

    async def _view_estimate_node(self, state: AgentState) -> dict:
        """View a specific estimate."""
        estimate_number = state.get("estimate_number")
        estimate_id = state.get("estimate_id")

        if not estimate_number and not estimate_id:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which estimate would you like to view?\n\n"
                           "Example: 'Show estimate E-20260102-0001'"
                )]
            }

        async with get_db_context() as db:
            estimate_service = EstimateService(db)

            if estimate_id:
                estimate = await estimate_service.get_estimate(estimate_id)
            else:
                # Find by number
                from sqlalchemy import select
                from models import Estimate as EstimateModel
                result = await db.execute(
                    select(EstimateModel).where(EstimateModel.estimate_number == estimate_number)
                )
                est = result.scalar_one_or_none()
                if est:
                    estimate = await estimate_service.get_estimate(est.id)
                else:
                    estimate = None

            if not estimate:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Estimate not found.")]
                }

            customer_name = estimate.customer.name if estimate.customer else f"Customer #{estimate.customer_id}"

            line_items = []
            for item in estimate.line_items:
                line_items.append({
                    "id": item.id,
                    "estimate_id": item.estimate_id,
                    "item_id": item.item_id,
                    "description": item.description,
                    "quantity": float(item.quantity),
                    "unit_price": float(item.unit_price),
                    "discount_pct": float(item.discount_pct or 0),
                    "notes": item.notes,
                    "line_total": float(item.line_total),
                    "tax_amount": float(item.tax_amount or 0),
                    "atp_status": item.atp_status.value if item.atp_status else None,
                    "atp_available_qty": float(item.atp_available_qty) if item.atp_available_qty else None,
                    "atp_shortage_qty": float(item.atp_shortage_qty) if item.atp_shortage_qty else None,
                    "atp_lead_time_days": item.atp_lead_time_days,
                    "sort_order": item.sort_order or 0,
                    "created_at": item.created_at.isoformat()
                })

            return {
                "response_type": "estimate_card",
                "response_data": {
                    "estimate": {
                        "id": estimate.id,
                        "estimate_number": estimate.estimate_number,
                        "version": estimate.version,
                        "parent_estimate_id": estimate.parent_estimate_id,
                        "customer_id": estimate.customer_id,
                        "customer_name": customer_name,
                        "status": estimate.status.value,
                        "currency_code": estimate.currency_code,
                        "valid_until": estimate.valid_until.isoformat() if estimate.valid_until else None,
                        "requested_delivery_date": estimate.requested_delivery_date.isoformat() if estimate.requested_delivery_date else None,
                        "earliest_delivery_date": estimate.earliest_delivery_date.isoformat() if estimate.earliest_delivery_date else None,
                        "delivery_feasible": estimate.delivery_feasible,
                        "notes": estimate.notes,
                        "subtotal": float(estimate.subtotal or 0),
                        "tax_amount": float(estimate.tax_amount or 0),
                        "total_amount": float(estimate.total_amount or 0),
                        "margin_percent": float(estimate.margin_percent) if estimate.margin_percent else None,
                        "rejection_reason": estimate.rejection_reason,
                        "created_at": estimate.created_at.isoformat(),
                        "updated_at": estimate.updated_at.isoformat(),
                        "line_items": line_items
                    }
                },
                "messages": [AIMessage(
                    content=f"Here's estimate **{estimate.estimate_number}** for {customer_name}."
                )]
            }

    async def _submit_estimate_node(self, state: AgentState) -> dict:
        """Submit estimate for approval."""
        estimate_number = state.get("estimate_number")

        if not estimate_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which estimate would you like to submit?\n\n"
                           "Example: 'Submit estimate E-20260102-0001'"
                )]
            }

        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Estimate as EstimateModel

            result = await db.execute(
                select(EstimateModel).where(EstimateModel.estimate_number == estimate_number)
            )
            estimate = result.scalar_one_or_none()

            if not estimate:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Estimate {estimate_number} not found.")]
                }

            estimate_service = EstimateService(db)
            try:
                await estimate_service.submit_for_approval(estimate.id)
                await db.commit()
                estimate = await estimate_service.get_estimate(estimate.id)

                return {
                    "response_type": "confirmation",
                    "response_data": {
                        "estimate_number": estimate.estimate_number,
                        "status": estimate.status.value,
                        "message": f"Estimate {estimate.estimate_number} submitted for approval"
                    },
                    "messages": [AIMessage(
                        content=f"**Estimate Submitted!**\n\n"
                               f"Estimate **{estimate.estimate_number}** has been submitted for approval.\n"
                               f"Status: **{estimate.status.value}**"
                    )]
                }
            except ValueError as e:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=str(e))]
                }

    async def _approve_estimate_node(self, state: AgentState) -> dict:
        """Approve a pending estimate."""
        estimate_number = state.get("estimate_number")

        if not estimate_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which estimate would you like to approve?\n\n"
                           "Example: 'Approve estimate E-20260102-0001'"
                )]
            }

        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Estimate as EstimateModel

            result = await db.execute(
                select(EstimateModel).where(EstimateModel.estimate_number == estimate_number)
            )
            estimate = result.scalar_one_or_none()

            if not estimate:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Estimate {estimate_number} not found.")]
                }

            estimate_service = EstimateService(db)
            try:
                await estimate_service.approve(estimate.id, approved_by=1)
                await db.commit()
                estimate = await estimate_service.get_estimate(estimate.id)

                return {
                    "response_type": "confirmation",
                    "response_data": {
                        "estimate_number": estimate.estimate_number,
                        "status": estimate.status.value
                    },
                    "messages": [AIMessage(
                        content=f"**Estimate Approved!**\n\n"
                               f"Estimate **{estimate.estimate_number}** has been approved.\n"
                               f"You can now send it to the customer."
                    )]
                }
            except ValueError as e:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=str(e))]
                }

    async def _reject_estimate_node(self, state: AgentState) -> dict:
        """Reject a pending estimate."""
        estimate_number = state.get("estimate_number")
        rejection_reason = state.get("rejection_reason") or "No reason provided"

        if not estimate_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which estimate would you like to reject?\n\n"
                           "Example: 'Reject estimate E-20260102-0001 because pricing too low'"
                )]
            }

        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Estimate as EstimateModel

            result = await db.execute(
                select(EstimateModel).where(EstimateModel.estimate_number == estimate_number)
            )
            estimate = result.scalar_one_or_none()

            if not estimate:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Estimate {estimate_number} not found.")]
                }

            estimate_service = EstimateService(db)
            try:
                await estimate_service.reject(estimate.id, reason=rejection_reason)
                await db.commit()

                return {
                    "response_type": "confirmation",
                    "response_data": {
                        "estimate_number": estimate.estimate_number,
                        "status": "rejected",
                        "reason": rejection_reason
                    },
                    "messages": [AIMessage(
                        content=f"**Estimate Rejected**\n\n"
                               f"Estimate **{estimate_number}** has been rejected.\n"
                               f"Reason: {rejection_reason}"
                    )]
                }
            except ValueError as e:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=str(e))]
                }

    async def _send_estimate_node(self, state: AgentState) -> dict:
        """Send estimate to customer."""
        estimate_number = state.get("estimate_number")

        if not estimate_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which estimate would you like to send?\n\n"
                           "Example: 'Send estimate E-20260102-0001 to customer'"
                )]
            }

        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Estimate as EstimateModel

            result = await db.execute(
                select(EstimateModel).where(EstimateModel.estimate_number == estimate_number)
            )
            estimate = result.scalar_one_or_none()

            if not estimate:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Estimate {estimate_number} not found.")]
                }

            estimate_service = EstimateService(db)
            try:
                await estimate_service.send_to_customer(estimate.id)
                await db.commit()

                return {
                    "response_type": "confirmation",
                    "response_data": {
                        "estimate_number": estimate.estimate_number,
                        "status": "sent"
                    },
                    "messages": [AIMessage(
                        content=f"**Estimate Sent!**\n\n"
                               f"Estimate **{estimate_number}** has been sent to the customer.\n"
                               f"Waiting for customer response."
                    )]
                }
            except ValueError as e:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=str(e))]
                }

    async def _accept_estimate_node(self, state: AgentState) -> dict:
        """Mark estimate as accepted by customer."""
        estimate_number = state.get("estimate_number")

        if not estimate_number:
            return {
                "response_type": "clarification",
                "messages": [AIMessage(
                    content="Which estimate did the customer accept?\n\n"
                           "Example: 'Customer accepted E-20260102-0001'"
                )]
            }

        async with get_db_context() as db:
            from sqlalchemy import select
            from models import Estimate as EstimateModel

            result = await db.execute(
                select(EstimateModel).where(EstimateModel.estimate_number == estimate_number)
            )
            estimate = result.scalar_one_or_none()

            if not estimate:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=f"Estimate {estimate_number} not found.")]
                }

            estimate_service = EstimateService(db)
            try:
                await estimate_service.accept(estimate.id)
                await db.commit()

                return {
                    "response_type": "confirmation",
                    "response_data": {
                        "estimate_number": estimate.estimate_number,
                        "status": "accepted"
                    },
                    "messages": [AIMessage(
                        content=f"**Estimate Accepted!**\n\n"
                               f"Estimate **{estimate_number}** has been marked as accepted.\n"
                               f"You can now create a job from this estimate."
                    )]
                }
            except ValueError as e:
                return {
                    "response_type": "error",
                    "messages": [AIMessage(content=str(e))]
                }

    async def _help_node(self, state: AgentState) -> dict:
        """Help Node - Shows available commands and examples."""
        help_text = """**Quantum HUB Quick Help**

**Estimates:**
- "create estimate for Acme Corp"
- "show my estimates" / "view estimate E-20260102-0001"
- "submit estimate E-xxx" / "approve estimate" / "send estimate"

**Quoting:**
- "I need a quote for 10 aluminum brackets"
- "list quotes" / "view quote Q-20251231-0001"
- "accept the balanced option"

**Jobs:**
- "create job for Acme Corp - 50 steel brackets"
- "list jobs" / "show job J-20251231-0001"
- "update job priority to 8"
- "attach PO-12345 to job"

**Inventory:**
- "show inventory" / "check stock for aluminum"
- "what's running low?"
- "reorder titanium" / "add 50 units of steel"

**Customers:**
- "list customers" / "add customer Widget Inc"

**Machines & Scheduling:**
- "list machines" / "add machine Laser-2 at $150/hr"
- "show schedule" / "find slot for 4 hours on CNC"

**Reports:**
- "show jobs on financial hold"
- "machine utilization"

Type naturally - I'll understand what you need!"""

        return {
            "messages": [AIMessage(content=help_text)],
            "response_type": "help",
            "response_data": {"topic": "general_help"}
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
            "customer_email": None,
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
            "item_sku": None,
            "item_cost": None,
            "item_category": None,
            "inventory_data": None,
            "schedule_data": None,
            "cost_data": None,
            "quote_options": None,
            "quote_number": None,
            "reorder_quantity": None,
            "machine_name": None,
            "hourly_rate": None,
            "new_priority": None,
            "new_delivery_date": None,
            "estimate_id": None,
            "estimate_number": None,
            "rejection_reason": None,
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
