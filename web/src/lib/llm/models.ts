export function filterProblematicModels(modelNames: string[]): string[] {
  // Extra client-side safety check to make sure problematic models never appear
  return modelNames.filter(name => name !== "o1-2024-12-17");
} 