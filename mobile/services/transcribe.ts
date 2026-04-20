import * as FileSystem from 'expo-file-system/legacy';
import api from './api';

export async function transcribeAudio(fileUri: string): Promise<string> {
  const base64 = await FileSystem.readAsStringAsync(fileUri, {
    encoding: FileSystem.EncodingType.Base64,
  });

  const ext = fileUri.split('.').pop() ?? 'm4a';
  const { data } = await api.post<{ text: string }>('/chat/transcribe', {
    audio_base64: base64,
    audio_format: ext,
  });
  return data.text;
}
