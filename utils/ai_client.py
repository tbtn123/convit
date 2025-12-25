import asyncio
from llama_cpp import Llama
import os
from concurrent.futures import ThreadPoolExecutor
import time
import json


class AI:
    _model = None
    _semaphore = None
    _executor = ThreadPoolExecutor(max_workers=4)

    def __init__(self, bot, model_path="AIChatbotIntegrate/phi-2-chat.q2_k.gguf"):  # VIT AI model using phi-2
        self.bot = bot
        self.model_path = model_path

        if not AI._model:
            print("Loading VIT AI model...")
            AI._model = Llama(
                model_path=self.model_path,
                n_ctx=1024,  # Increased context window to handle larger prompts
                n_threads=12,  # Use multiple threads for better performance
                n_gpu_layers=0,  # CPU only for now (ARM64 compatible)
                verbose=False,
            )
        if not AI._semaphore:
            AI._semaphore = asyncio.Semaphore(1)
        self.model = AI._model
        self.semaphore = AI._semaphore

    async def ask_simple(self, prompt: str, max_tokens: int = 96) -> str:
        """Simple ask method for general questions"""
        start_time = time.time()

        # Enhanced prompt formatting for better responses
        full_prompt = f"""You are VIT, an AI assistant that answers questions directly and concisely.

User: {prompt}
Assistant:"""

        # Use shared semaphore for thread safety
        async with self.semaphore:
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                None,
                lambda: self.model(
                    full_prompt,
                    max_tokens=max_tokens,
                    temperature=0.3,  # Slightly higher temperature for better responses
                    top_p=0.9,
                    repeat_penalty=1.1,
                    stop=["User:", "Assistant:", "\n\n"]
                )
            )

        response = output["choices"][0]["text"].strip()
        end_time = time.time()
        print(f"VIT AI response time: {end_time - start_time:.2f}s")
        return response

    async def ask_json(self, prompt: str, max_tokens: int = 200) -> str:
        """Ask method optimized for JSON responses"""
        start_time = time.time()

        # Build prompt based on working AIChatbotIntegrate example, customized for JSON
        full_prompt = f"""You are a helpful assistant that returns ONLY valid JSON.
{prompt}
Assistant (JSON):"""

        # Use shared semaphore for thread safety
        async with self.semaphore:
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                None,
                lambda: self.model(
                    full_prompt,
                    max_tokens=max_tokens,
                    temperature=0.0,
                    repeat_penalty=1.1,
                    stop=["User:", "Assistant:", "\n\n", "```", "```json", "```JSON"]
                )
            )

        response = output["choices"][0]["text"].strip()
        end_time = time.time()
        print(f"VIT AI JSON response time: {end_time - start_time:.2f}s")
        return response

    async def process_messages_batch(self, messages: list, batch_size: int = 20) -> dict:
        """Process large message sets in batches without increasing context window"""
        if len(messages) <= batch_size:
            # If small enough, process normally
            return await self.analyze_message_batch(messages)

        # Process in batches and aggregate results
        all_scores = {}
        summaries = []

        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            batch_result = await self.analyze_message_batch(batch)

            # Aggregate scores
            for score_entry in batch_result.get("scores", []):
                user = score_entry["user"]
                score = score_entry["score"]
                if user not in all_scores:
                    all_scores[user] = []
                all_scores[user].append(score)

            # Collect summaries
            if "message" in batch_result:
                summaries.append(batch_result["message"])

        # Calculate final aggregated scores (average)
        final_scores = []
        for user, scores in all_scores.items():
            avg_score = sum(scores) / len(scores)
            # Convert to 1 or -1 based on average
            final_score = 1 if avg_score >= 0 else -1
            final_scores.append({"user": user, "score": final_score})

        # Combine summaries
        combined_summary = await self.combine_summaries(summaries)

        return {
            "message": combined_summary,
            "scores": final_scores
        }

    async def analyze_message_batch(self, messages: list) -> dict:
        """Analyze a small batch of messages that fits in context window"""
        # If too many messages, process in sub-batches to avoid AI confusion
        if len(messages) > 8:
            # Split into smaller sub-batches and combine results
            sub_batch_size = 8
            all_scores = {}
            summaries = []

            for i in range(0, len(messages), sub_batch_size):
                sub_batch = messages[i:i + sub_batch_size]
                sub_result = await self.analyze_message_batch(sub_batch)

                # Aggregate scores
                for score_entry in sub_result.get("scores", []):
                    user = score_entry["user"]
                    score = score_entry["score"]
                    if user not in all_scores:
                        all_scores[user] = []
                    all_scores[user].append(score)

                # Collect summaries
                if "message" in sub_result and sub_result["message"] != "Analysis failed":
                    summaries.append(sub_result["message"])

            # Calculate final aggregated scores
            final_scores = []
            for user, scores in all_scores.items():
                avg_score = sum(scores) / len(scores)
                final_score = 1 if avg_score >= 0 else -1
                final_scores.append({"user": user, "score": final_score})

            # Combine summaries
            combined_summary = await self.combine_summaries(summaries)

            return {
                "message": combined_summary,
                "scores": final_scores
            }

        message_text = "\n".join(f'{msg["username"]}: {msg["text"]}' for msg in messages)

        # Get unique usernames from this batch
        unique_users = list(set(msg["username"] for msg in messages))

        prompt = f"""
You are analyzing Discord chat messages.

TASK:
1. Read all messages carefully.
2. Write ONE short summary describing what happened overall.
3. Score each user's behavior using this rule:
   - +1 = helpful, polite, constructive
   - -1 = rude, harmful, disruptive
   - 0 = neutral or unclear

IMPORTANT RULES:
- You MUST include EVERY user listed.
- If a user's behavior is neutral or unclear, use score 0.
- Do NOT guess intent beyond the text.
- Do NOT include explanations or extra text.

USERS TO SCORE:
{', '.join(unique_users)}

MESSAGES:
{message_text}

OUTPUT REQUIREMENTS:
- Output ONLY valid JSON
- No markdown
- No comments
- No text before or after JSON
- Follow the exact format below

JSON FORMAT:
{{
  "message": "short neutral summary",
  "scores": [
    {{"user": "username", "score": 0}}
  ]
}}

If you cannot follow these rules, output an empty JSON object: {{}}
"""

        result = await self.ask_json(prompt, max_tokens=150)

        def extract_json_from_response(response_text):
            # Debug: print raw response
            print(f"[DEBUG] Raw AI response: '{response_text[:200]}...'")

            text = response_text.strip()
            if text.startswith("```"):
                text = text.strip("`\n ")
                if text.lower().startswith("json"):
                    text = text[4:].strip()

            # Try to find JSON object
            start_idx = text.find('{')
            if start_idx != -1:
                brace_count = 0
                end_idx = start_idx
                for i, char in enumerate(text[start_idx:], start_idx):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            try:
                                json_str = text[start_idx:end_idx]
                                parsed = json.loads(json_str)
                                if "message" in parsed and "scores" in parsed:
                                    print(f"[DEBUG] Successfully parsed JSON: {parsed}")
                                    return parsed
                            except json.JSONDecodeError:
                                continue
                            break

            # Fallback: try to extract using regex
            import re
            message_match = re.search(r'"message"\s*:\s*"([^"]*)"', text)
            scores_matches = re.findall(r'"user"\s*:\s*"([^"]+)"\s*,\s*"score"\s*:\s*([0-9\-]+)', text)

            if message_match or scores_matches:
                message = message_match.group(1) if message_match else "Analysis completed."
                scores = [{"user": user, "score": int(score)} for user, score in scores_matches]
                if scores:
                    result = {"message": message, "scores": scores}
                    print(f"[DEBUG] Constructed JSON from regex: {result}")
                    return result

            print(f"[DEBUG] JSON extraction failed")
            return None

        parsed = extract_json_from_response(result)
        return parsed if parsed else {"message": "Analysis failed", "scores": []}

    async def combine_summaries(self, summaries: list) -> str:
        """Combine multiple batch summaries into one coherent summary"""
        if len(summaries) == 1:
            return summaries[0]

        # Filter out empty or failed summaries
        valid_summaries = [s for s in summaries if s and s.strip() and "Analysis failed" not in s]
        if not valid_summaries:
            return "Chat analysis completed but summary generation failed."

        if len(valid_summaries) == 1:
            return valid_summaries[0]

        summaries_text = "\n".join(f"Summary {i+1}: {s}" for i, s in enumerate(valid_summaries))

        # Use a better prompt format for combination
        prompt = f"""You are an AI assistant that combines multiple chat message summaries into one coherent summary.

Here are the summaries to combine:
{summaries_text}

Please create one single, coherent summary that captures the main points from all these summaries. Be concise but informative.

Combined summary:"""

        # Use ask_simple but with a modified approach for better results
        full_prompt = f"""You are VIT, an assistant that summarizes information clearly and concisely.

User: {prompt}
Assistant:"""

        # Use shared semaphore for thread safety
        async with self.semaphore:
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                None,
                lambda: self.model(
                    full_prompt,
                    max_tokens=120,
                    temperature=0.3,
                    stop=["User:", "Assistant:", "\n\n"]
                )
            )

        result = output["choices"][0]["text"].strip()
        return result if result else "Multiple chat segments analyzed successfully."
