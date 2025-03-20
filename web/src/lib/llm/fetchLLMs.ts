import { LLMProviderDescriptor } from "@/app/admin/configuration/llm/interfaces";
import { fetchSS } from "../utilsSS";
import { filterProblematicModels } from "./models";

export async function fetchLLMProvidersSS() {
  const response = await fetchSS("/llm/provider");
  if (response.ok) {
    const providers = await response.json() as LLMProviderDescriptor[];
    
    // Filter out problematic models from each provider
    return providers.map(provider => ({
      ...provider,
      model_names: filterProblematicModels(provider.model_names),
      display_model_names: provider.display_model_names 
        ? filterProblematicModels(provider.display_model_names) 
        : null
    }));
  }
  return [];
}
