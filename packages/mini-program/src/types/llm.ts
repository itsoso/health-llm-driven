/**
 * browser-llm-orchestrator 相关类型定义
 */

export type LLMSite = 'chatgpt' | 'gemini' | 'grok' | 'claude' | string;
export type AdapterMode = 'browser' | 'api';
export type BatchStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'partial' | 'cancelled';

export interface ModelResult {
  llm_site: string;
  model_version: string;
  status: BatchStatus;
  result_content?: string;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  elapsed_seconds?: number;
}

export interface BatchTask {
  status: string;
  current_stage?: string;
  stage_progress?: string;
  model_results: ModelResult[];
  aggregation_result?: string;
  completed_at?: string;
}

export interface Batch {
  batch_id: string;
  title?: string;
  prompt: string;
  llm_sites: string[];
  model_versions?: Record<string, string>;
  aggregator_site?: string;
  aggregator_model?: string;
  adapter_mode?: AdapterMode;
  site_modes?: Record<string, string>;
  status: BatchStatus;
  created_at: string;
  completed_at?: string;
  total_elapsed_seconds?: number;
  error_message?: string;
  has_images?: boolean;
  image_count?: number;
  result_path?: string;
  task: BatchTask;
}

export interface CreateBatchParams {
  prompt: string;
  title?: string;
  llm_sites: string[];
  model_versions?: Record<string, string>;
  aggregator_site?: string;
  aggregator_model?: string;
  aggregator_prompt?: string;
  adapter_mode?: AdapterMode;
  site_modes?: Record<string, string>;
  images?: string[];
  web_search_enabled?: boolean;
}

export interface HistoryItem {
  batch_id: string;
  title?: string;
  prompt: string;
  status: BatchStatus;
  created_at: string;
  completed_at?: string;
  llm_sites: string[];
  aggregator_site?: string;
  total_elapsed_seconds?: number;
  task?: BatchTask;
}

export interface PromptTemplate {
  id: string;
  name: string;
  prompt: string;
  type: string;
  scene_type?: string;
  description?: string;
  tags?: string[];
}

export interface SchedulerTask {
  id: string;
  type: string;
  name: string;
  cron: string;
  enabled: boolean;
  last_run_at?: string;
  last_status?: string;
  last_error?: string;
  run_count: number;
  success_count: number;
  fail_count: number;
}

// LLM 站点显示信息
export const LLM_SITE_INFO: Record<string, { name: string; icon: string }> = {
  chatgpt: { name: 'ChatGPT', icon: '🤖' },
  gemini: { name: 'Gemini', icon: '✨' },
  grok: { name: 'Grok', icon: '🧠' },
  claude: { name: 'Claude', icon: '🎭' },
  'lb-gemini-3-pro': { name: 'Gemini 3 Pro', icon: '✨' },
  'lb-claude-4.5-sonnet': { name: 'Claude 4.5', icon: '🎭' },
  'lb-gpt-5.1': { name: 'GPT 5.1', icon: '🤖' },
  'lb-claude-4-sonnet-think': { name: 'Claude 4 Think', icon: '🎭' },
};

export function getSiteInfo(site: string): { name: string; icon: string } {
  return LLM_SITE_INFO[site] || { name: site, icon: '🔮' };
}
