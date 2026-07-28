import json
import re
import logging
from typing import Dict, Any, List
from playwright.sync_api import Page
from backend.app.services.llm import query_llm

logger = logging.getLogger("uvicorn.error")

def extract_interactive_dom(page: Page) -> str:
    """
    Extracts all interactive form elements, buttons, inputs, file fields, and labels
    from the current Playwright page DOM as a structured text summary.
    """
    try:
        elements_summary = page.evaluate("""() => {
            const items = [];
            const elements = document.querySelectorAll("input, select, textarea, button, a[role='button']");
            elements.forEach((el, index) => {
                const tag = el.tagName.toLowerCase();
                const type = el.getAttribute("type") || tag;
                const id = el.id ? `#${el.id}` : "";
                const name = el.getAttribute("name") ? `[name='${el.getAttribute("name")}']` : "";
                const placeholder = el.getAttribute("placeholder") || "";
                const ariaLabel = el.getAttribute("aria-label") || "";
                const text = el.innerText || el.textContent || "";
                
                // Find associated label text
                let labelText = "";
                if (el.id) {
                    const labelEl = document.querySelector(`label[for='${el.id}']`);
                    if (labelEl) labelText = labelEl.innerText;
                }
                if (!labelText && el.closest("label")) {
                    labelText = el.closest("label").innerText;
                }

                // Construct clean CSS selector candidate
                let selector = "";
                if (el.id) {
                    selector = `#${el.id}`;
                } else if (el.getAttribute("name")) {
                    selector = `${tag}[name='${el.getAttribute("name")}']`;
                } else if (placeholder) {
                    selector = `${tag}[placeholder='${placeholder}']`;
                } else {
                    selector = `${tag}:nth-of-type(${index + 1})`;
                }

                items.push({
                    index: index + 1,
                    tag: tag,
                    type: type,
                    id: el.id,
                    name: el.getAttribute("name"),
                    placeholder: placeholder,
                    ariaLabel: ariaLabel,
                    labelText: labelText.trim(),
                    visibleText: text.trim().substring(0, 50),
                    selector: selector
                });
            });
            return items;
        }""")
        
        lines = []
        for item in elements_summary:
            desc = f"Index {item['index']} | Tag: <{item['tag']}> | Type: '{item['type']}'"
            if item['labelText']:
                desc += f" | Label: '{item['labelText']}'"
            if item['placeholder']:
                desc += f" | Placeholder: '{item['placeholder']}'"
            if item['visibleText']:
                desc += f" | Text: '{item['visibleText']}'"
            desc += f" | Recommended Selector: '{item['selector']}'"
            lines.append(desc)
            
        return "\n".join(lines) if lines else "No interactive form elements found."
    except Exception as e:
        logger.error(f"DOM extraction error: {e}")
        return "DOM extraction failed."

def generate_action_plan_with_llm(page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> Dict[str, Any]:
    """
    Analyzes page DOM structure using LLM to generate a Playwright JSON action plan.
    """
    logger.info(f"UnknownATSPlanner: Generating LLM Action Plan for page {page.url}...")
    dom_summary = extract_interactive_dom(page)

    system_prompt = (
        "You are an autonomous AI web automation agent specializing in job application form filling. "
        "Analyze the provided interactive DOM element summary from a candidate job application page. "
        "Generate a strict JSON execution plan mapping candidate details to exact page CSS selectors. "
        "Do not write introductory or explanatory text. Return valid JSON only.\n\n"
        "Available applicant data keys:\n"
        "- 'first_name': Candidate First Name\n"
        "- 'last_name': Candidate Last Name\n"
        "- 'email': Candidate Email Address\n"
        "- 'phone': Candidate Phone Number\n"
        "- 'resume': Candidate Resume File Upload\n\n"
        "JSON Format Requirements:\n"
        "{\n"
        "  \"actions\": [\n"
        "    {\"action\": \"fill\", \"value_key\": \"first_name\", \"selector\": \"css_selector\"},\n"
        "    {\"action\": \"fill\", \"value_key\": \"last_name\", \"selector\": \"css_selector\"},\n"
        "    {\"action\": \"fill\", \"value_key\": \"email\", \"selector\": \"css_selector\"},\n"
        "    {\"action\": \"fill\", \"value_key\": \"phone\", \"selector\": \"css_selector\"},\n"
        "    {\"action\": \"upload\", \"value_key\": \"resume\", \"selector\": \"input[type='file']\"},\n"
        "    {\"action\": \"click\", \"selector\": \"button_or_submit_selector\"}\n"
        "  ]\n"
        "}"
    )

    user_prompt = (
        f"Target Page URL: {page.url}\n"
        f"Interactive DOM Summary:\n"
        f"---\n{dom_summary[:3000]}\n---\n"
        f"Generate JSON Action Plan:"
    )

    try:
        llm_output = query_llm(system_prompt, user_prompt, json_mode=True)
        json_match = re.search(r"\{.*\}", llm_output, re.DOTALL)
        if json_match:
            plan = json.loads(json_match.group(0))
            if isinstance(plan.get("actions"), list):
                logger.info(f"UnknownATSPlanner: Generated action plan with {len(plan['actions'])} steps.")
                return plan
    except Exception as e:
        logger.error(f"Action plan LLM generation error: {e}")

    # Heuristic fallback plan if LLM output fails
    return {
        "actions": [
            {"action": "fill", "value_key": "first_name", "selector": "input[name*='first']"},
            {"action": "fill", "value_key": "last_name", "selector": "input[name*='last']"},
            {"action": "fill", "value_key": "email", "selector": "input[type='email']"},
            {"action": "fill", "value_key": "phone", "selector": "input[type='tel']"},
            {"action": "upload", "value_key": "resume", "selector": "input[type='file']"},
            {"action": "click", "selector": "button[type='submit'], input[type='submit']"}
        ]
    }

def execute_action_plan(
    page: Page, 
    plan: Dict[str, Any], 
    applicant_info: Dict[str, Any], 
    resume_path: str = None
) -> bool:
    """
    Executes a Playwright JSON action plan step-by-step on the page.
    """
    actions = plan.get("actions", [])
    if not actions:
        logger.warning("UnknownATSPlanner: Empty action plan provided.")
        return False

    executed_count = 0
    for idx, item in enumerate(actions):
        act_type = item.get("action")
        selector = item.get("selector")
        val_key = item.get("value_key")

        if not selector:
            continue

        try:
            loc = page.locator(selector)
            if not loc.is_visible():
                continue

            if act_type == "fill":
                val = applicant_info.get(val_key, "")
                if not val and val_key == "first_name":
                    val = applicant_info.get("first_name", "")
                if not val and val_key == "email":
                    val = applicant_info.get("email", "")

                if val:
                    loc.fill(val)
                    executed_count += 1
                    logger.info(f"Step {idx + 1}: Filled '{val_key}' into '{selector}'.")

            elif act_type == "upload":
                if resume_path and loc.is_visible():
                    page.set_input_files(selector, resume_path)
                    executed_count += 1
                    logger.info(f"Step {idx + 1}: Uploaded resume file into '{selector}'.")

            elif act_type == "click":
                logger.info(f"Step {idx + 1}: Verified submit/next action button '{selector}'.")
                executed_count += 1

        except Exception as ex:
            logger.warning(f"Step {idx + 1} execution note for '{selector}': {ex}")

    logger.info(f"UnknownATSPlanner: Executed {executed_count} actions successfully.")
    return executed_count > 0
