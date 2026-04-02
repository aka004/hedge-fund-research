import Anthropic from '@anthropic-ai/sdk';

const MODEL = 'claude-sonnet-4-20250514';
const MAX_TOKENS = 4096;

let anthropic = null;

function getClient() {
  if (!anthropic) {
    if (!process.env.ANTHROPIC_API_KEY) {
      throw new Error('ANTHROPIC_API_KEY not set — check .env file');
    }
    anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  }
  return anthropic;
}

/**
 * Call Claude with the given system prompt and conversation messages.
 * Returns the raw text response.
 */
export async function callClaude(systemPrompt, messages) {
  const response = await getClient().messages.create({
    model: MODEL,
    max_tokens: MAX_TOKENS,
    system: systemPrompt,
    messages,
  });
  return response.content[0].text;
}
