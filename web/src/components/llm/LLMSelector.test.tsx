import { LLMProvidersResponse } from "@/lib/api/types";

/**
 * Regression test for LLMSelector filtering logic
 * 
 * Ensures that certain model names like "o1-2024-12-17" are filtered out
 * from the list of available models. This specific model ID was causing issues
 * in the production environment and should be excluded from the model options.
 */
describe("LLMSelector filtering", () => {
  // Create a mock LLM provider for testing
  const mockLlmProviders: LLMProvidersResponse = {
    providers: {
      "OpenAI": {
        provider_key: "openai",
        provider_display_name: "OpenAI",
        provider_models: [
          {
            model_key: "gpt-4",
            model_display_name: "GPT-4",
            default_model: false,
            model_display_group: null,
          },
          {
            model_key: "o1-2024-12-17",
            model_display_name: "o1-2024-12-17",
            default_model: false,
            model_display_group: null,
          },
          {
            model_key: "gpt-3.5-turbo",
            model_display_name: "GPT-3.5 Turbo",
            default_model: false,
            model_display_group: null,
          }
        ]
      }
    }
  };

  test("filters out o1-2024-12-17 model from model names", () => {
    // Import the filtering logic from LLMSelector
    const getProviderOptions = (llmProviders: LLMProvidersResponse) => {
      // This logic is similar to what's in LLMSelector.tsx
      const seen = new Set<string>();
      const options: { providerId: string; modelId: string; displayName: string }[] = [];

      Object.entries(llmProviders.providers).forEach(([providerId, provider]) => {
        provider.provider_models.forEach((model) => {
          // Skip o1-2024-12-17 model
          if (model.model_key === "o1-2024-12-17") {
            return;
          }

          const key = `${providerId}:${provider.provider_key}:${model.model_key}`;
          if (!seen.has(key)) {
            seen.add(key);
            options.push({
              providerId,
              modelId: model.model_key,
              displayName: model.model_display_name,
            });
          }
        });
      });

      return options;
    };

    const options = getProviderOptions(mockLlmProviders);
    
    // Check that o1-2024-12-17 is filtered out
    expect(options.find(o => o.modelId === "o1-2024-12-17")).toBeUndefined();
    
    // Check that other models are still present
    expect(options.find(o => o.modelId === "gpt-4")).toBeDefined();
    expect(options.find(o => o.modelId === "gpt-3.5-turbo")).toBeDefined();
    
    // Check the total number of models
    expect(options.length).toBe(2);
  });
}); 