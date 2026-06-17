"""
labguru_mcp.prompts
-------------------
MCP prompts that encode the recurring Labguru business workflows as guided,
parameterised procedures. A prompt returns an instruction the client model
follows using the registered tools; it does not call the API itself.
"""

from __future__ import annotations

from .app import mcp


@mcp.prompt(title="Generate a purchase order")
def generate_purchase_order(order_number: str) -> str:
    """Guide the assistant through reviewing and summarising a purchase order."""
    return (
        f"Help me prepare the purchase order for order number {order_number}.\n\n"
        "Steps:\n"
        f"1. Call get_order('{order_number}') to list the line items.\n"
        f"2. Call get_order_summary('{order_number}') for the financial totals.\n"
        "3. Check whether every item is approved (status == 'approved' or "
        "'submitted'). Flag any still 'pending'.\n"
        "4. Identify the manufacturer(s); if a manufacturer email is needed, use "
        "list_companies(search=...) then get_company(id).\n"
        "5. Present a clear summary: supplier, line items (name, qty, unit price), "
        "delivery/dry-ice/extra fees, and grand total.\n"
        "6. Only if I explicitly confirm, create the report with "
        "create_report(title='PO ...') and tag it with tag_report(...).\n\n"
        "Do not create or modify anything until I confirm."
    )


@mcp.prompt(title="CMR usage report")
def cmr_report(start_id: int, end_id: int) -> str:
    """Guide a CMR (Chemical Material Registry) usage scan over an experiment range."""
    return (
        "Produce a CMR (Chemical Material Registry) usage report for experiments "
        f"with IDs from {start_id} to {end_id} (inclusive).\n\n"
        "Steps:\n"
        "1. Call get_cmr_items() to get the CMR-flagged inventory items "
        "(name, sys_id, collection, type_of_risk). Build a sys_id -> risk lookup.\n"
        f"2. Call get_experiments_in_range({start_id}, {end_id}) to list experiments.\n"
        "3. For each experiment, call get_experiment_samples(id) and check whether "
        "any sample sys_id is in the CMR lookup.\n"
        "4. For every experiment that used at least one CMR product, record: owner, "
        "experiment id, title, date, the list of CMR products used, and their risk "
        "types.\n"
        "5. Present the result as a table sorted by experiment id. Note the total "
        "count of experiments scanned and how many used CMR products.\n\n"
        "Mind that wide ranges are slow; warn me before scanning very large ranges."
    )


@mcp.prompt(title="Duplicate an experiment")
def duplicate_experiment(experiment_id: int) -> str:
    """Guide inspecting an experiment before duplicating its structure."""
    return (
        f"Help me duplicate experiment {experiment_id}.\n\n"
        "Steps:\n"
        f"1. Call get_experiment({experiment_id}) to review its title, project, and "
        "procedure/section structure.\n"
        f"2. Call get_experiment_samples({experiment_id}) and "
        f"get_experiment_stock_ids({experiment_id}) to capture the reagents and "
        "stock links that must be preserved.\n"
        "3. Propose a plan: the new experiment title, target project, and which "
        "sections/elements and stock associations to recreate.\n"
        "4. After I confirm, create the new experiment with create_experiment(...), "
        "then recreate sections and elements with create_section(...) / "
        "create_element(...) as needed.\n\n"
        "Do not create anything until I approve the plan."
    )


@mcp.prompt(title="Safety data sheet links")
def safety_data_sheets(collections: str = "") -> str:
    """Guide exporting safety data sheet (fiche de securite) links."""
    target = f"('{collections}')" if collections else "()"
    return (
        "Collect the safety data sheet (fiche de securite) web links for inventory "
        "items.\n\n"
        f"1. Call get_safety_links{target} to get name, sys_id, collection, url for "
        "every item that has a linked page.\n"
        "2. Group the results by collection and present them as a readable list or "
        "table.\n"
        "3. Flag any item missing a link if I ask for completeness."
    )
