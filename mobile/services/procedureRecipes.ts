import api from './api';

/**
 * 程序性记忆/配方(Harness Slice 3)。
 * 配方 = 确定性重放的工具序列:触发短语精确匹配;每步确认门原样生效
 * (typed_only/never_auto 不被配方绕过)。后端 /agent/recipes*。
 */
export interface ProcedureRecipeStep {
  tool: string;
  args_template: Record<string, any>;
}

export interface ProcedureRecipe {
  id: number;
  name: string;
  trigger_phrases: string[];
  steps: ProcedureRecipeStep[];
  created_from_conversation_id: number | null;
  use_count: number;
  created_at: string | null;
}

export interface RecipeListResponse {
  recipes: ProcedureRecipe[];
  count: number;
}

/** 列出我的配方。失败向上抛,由 UI 显式呈现(不静默吞成假空态)。 */
export async function listRecipes(): Promise<ProcedureRecipe[]> {
  const { data } = await api.get<RecipeListResponse>('/agent/recipes');
  return Array.isArray(data?.recipes) ? data.recipes : [];
}

/** 删除配方。404/网络错误向上抛。 */
export async function deleteRecipe(recipeId: number): Promise<void> {
  await api.delete(`/agent/recipes/${recipeId}`);
}

/**
 * 从对话最近一轮工具序列存配方(后端已把候选步骤持久化在消息 meta 里,
 * 这里只提交命名 + 触发短语;不重放对话、不经 LLM)。
 */
export async function saveRecipeFromConversation(
  conversationId: number,
  payload: { name: string; trigger_phrases: string[] },
): Promise<ProcedureRecipe> {
  const { data } = await api.post<ProcedureRecipe>(
    `/agent/recipes/${conversationId}/save-from-conversation`,
    payload,
  );
  return data;
}
