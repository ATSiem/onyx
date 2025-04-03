import { ToolSnapshot } from "@/lib/tools/interfaces";
import { DocumentSet, MinimalUserSnapshot } from "@/lib/types";

export interface StarterMessageBase {
  message: string;
}
export interface StarterMessage extends StarterMessageBase {
  name: string;
}

export interface Prompt {
  id: number;
  name: string;
  description: string;
  system_prompt: string;
  task_prompt: string;
  include_citations: boolean;
  datetime_aware: boolean;
  default_prompt: boolean;
}
export interface Persona {
  id: number;
  name: string;
  description: string;
  is_public: boolean;
  is_visible: boolean;
  icon_shape?: number;
  icon_color?: string;
  uploaded_image_id?: string;
  user_file_ids: number[];
  user_folder_ids: number[];
  display_priority: number | null;
  is_default_persona: boolean;
  builtin_persona: boolean;
  starter_messages: StarterMessage[] | null;
  tools: ToolSnapshot[];
  labels?: PersonaLabel[];
  user_file_ids: number[];
  user_folder_ids: number[];
}

export interface PersonaLabel {
  id: number;
  name: string;
}
