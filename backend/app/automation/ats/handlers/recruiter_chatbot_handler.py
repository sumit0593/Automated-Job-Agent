import re
import logging
from typing import Dict, Any, Optional
from playwright.sync_api import Page
from backend.app.automation.ats.base_ats import BaseATS
from backend.app.services.llm import query_llm

logger = logging.getLogger("uvicorn.error")

def extract_latest_bot_question(page: Page) -> str:
    """
    Extracts the latest question/text message from chatbot conversation bubbles.
    """
    try:
        question = page.evaluate("""() => {
            // Check common chat bubble selectors for Paradox, Mya, Landbot, Eightfold, custom widgets
            const chatBubbleSelectors = [
                ".bot-message", ".chat-bubble-bot", ".msg-bot", "[data-author='bot']",
                ".st-chat-message-bot", ".chat-message-received", ".message.received",
                ".paradox-chat-message", ".olivia-message", ".landbot-message"
            ];
            
            for (const sel of chatBubbleSelectors) {
                const bubbles = document.querySelectorAll(sel);
                if (bubbles.length > 0) {
                    const lastBubble = bubbles[bubbles.length - 1];
                    return lastBubble.innerText || lastBubble.textContent || "";
                }
            }
            
            // Fallback: search for last paragraph or header inside chat containers
            const container = document.querySelector(".chat-container, .conversation-container, #chat-body, .widget-chat");
            if (container) {
                const paragraphs = container.querySelectorAll("p, span, div");
                if (paragraphs.length > 0) {
                    const lastP = paragraphs[paragraphs.length - 1];
                    return lastP.innerText || lastP.textContent || "";
                }
            }
            
            return "";
        }""")
        return question.strip() if question else ""
    except Exception as e:
        logger.error(f"Error extracting chatbot question: {e}")
        return ""

def generate_chatbot_answer_with_llm(
    question: str, 
    applicant_info: Dict[str, Any], 
    resume_text: str = ""
) -> str:
    """
    Uses QuestionClassifier to resolve candidate profile questions deterministically
    before invoking LLM reasoning.
    """
    from backend.app.services.matching.question_classifier import classify_and_resolve_question
    
    res = classify_and_resolve_question(question, applicant_info)
    logger.info(f"QuestionClassifier: Source='{res['source']}', Used LLM={res['used_llm']}")
    return res["answer"]

    system_prompt = (
        "You are an AI assistant acting on behalf of a job candidate in an automated recruiter chatbot interview. "
        "Answer the recruiter's question concisely, professionally, and accurately based ONLY on the provided candidate background. "
        "Rules:\n"
        "1. Keep answers concise (under 100 characters for general questions unless detailed response is asked).\n"
        "2. Do not invent fake degrees, companies, or facts.\n"
        "3. Do not include conversational filler like 'Sure!' or 'Here is my answer:'. Just provide the plain text answer.\n"
    )

    user_prompt = (
        f"Candidate Full Name: {full_name}\n"
        f"Candidate Email: {email}\n"
        f"Candidate Background/Resume:\n---\n{(resume_text or '')[:1500]}\n---\n"
        f"Recruiter Chatbot Question: '{question}'\n"
        f"Plain Text Answer:"
    )

    try:
        ans = query_llm(system_prompt, user_prompt, json_mode=False)
        if ans and len(ans.strip()) > 0:
            cleaned_ans = ans.strip().replace("\n", " ")
            # Ensure character limit if asked for short pitch
            if "why should we hire you" in q_lower or "under 100" in q_lower:
                return cleaned_ans[:100].strip()
            return cleaned_ans[:180].strip()
    except Exception as e:
        logger.error(f"LLM chatbot answer generation error: {e}")

    return f"Experienced Software Engineer specializing in Full Stack and AI engineering."

class RecruiterChatbotHandler(BaseATS):
    """
    Dedicated modular handler for AI Recruiter Chatbots (Paradox, Mya, Landbot, Eightfold, Chatspot).
    Orchestrates the dynamic Playwright conversational loop.
    """
    
    def apply(self, page: Page, applicant_info: Dict[str, Any], resume_path: str = None) -> bool:
        logger.info(f"RecruiterChatbotHandler: Starting AI Chatbot conversational loop on {page.url}...")
        try:
            page.wait_for_load_state("domcontentloaded")
            
            # Read resume text if available
            resume_text = ""
            if resume_path:
                try:
                    from backend.app.services.parser import extract_text_from_pdf
                    resume_text = extract_text_from_pdf(resume_path)
                except Exception:
                    pass

            max_turns = 12
            previous_question = ""

            for turn in range(1, max_turns + 1):
                page.wait_for_timeout(1500)
                
                # Check for conversation completion signals
                page_content = (page.content() or "").lower()
                if any(sig in page_content for sig in ["thank you for applying", "application complete", "we have received your application", "application submitted"]):
                    logger.info(f"RecruiterChatbotHandler: Detected application completion signal on turn {turn}.")
                    return True

                # Extract latest bot question
                bot_question = extract_latest_bot_question(page)
                if not bot_question or bot_question == previous_question:
                    logger.info(f"Turn {turn}: No new question detected. Waiting...")
                    page.wait_for_timeout(2000)
                    bot_question = extract_latest_bot_question(page)
                    if not bot_question or bot_question == previous_question:
                        logger.info(f"Turn {turn}: Conversation loop finished.")
                        break

                previous_question = bot_question
                logger.info(f"Turn {turn} Recruiter Question: '{bot_question}'")

                # Generate LLM answer
                answer = generate_chatbot_answer_with_llm(bot_question, applicant_info, resume_text)
                logger.info(f"Turn {turn} Generated Answer: '{answer}'")

                # Find chat input element
                input_selector = "input[type='text'], textarea, [contenteditable='true'], .chat-input, #chat-input"
                input_loc = page.locator(input_selector)

                if input_loc.count() > 0 and input_loc.first.is_visible():
                    input_loc.first.fill(answer)
                    page.wait_for_timeout(300)
                    
                    # Hit Enter or click Send button
                    send_btn = page.locator("button:has-text('Send'), button[type='submit'], .send-button, .chat-send")
                    if send_btn.count() > 0 and send_btn.first.is_visible():
                        send_btn.first.click()
                    else:
                        input_loc.first.press("Enter")
                        
                    logger.info(f"Turn {turn}: Sent answer successfully via Playwright.")
                else:
                    logger.warning(f"Turn {turn}: Could not locate visible chat input field.")
                    break

            return True
        except Exception as e:
            logger.error(f"RecruiterChatbotHandler error: {e}")
            return False
