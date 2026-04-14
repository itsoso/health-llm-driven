'use client';

import { useRef, useState } from 'react';
import { chatApi } from '@/services/api/ai';

interface UseMediaInputDeps {
  setInputText: React.Dispatch<React.SetStateAction<string>>;
  showToast: (msg: string, type?: 'success' | 'error' | 'info' | 'warning') => void;
}

export function useMediaInput({ setInputText, showToast }: UseMediaInputDeps) {
  const [isRecording, setIsRecording] = useState(false);
  const [imageUploading, setImageUploading] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [pendingImage, setPendingImage] = useState<{base64: string; type: string} | null>(null);
  const [pendingFile, setPendingFile] = useState<{base64: string; name: string} | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const clearPendingAttachment = () => { setImagePreview(null); setPendingImage(null); setPendingFile(null); };

  const handleVoiceToggle = async () => {
    if (isRecording) { mediaRecorderRef.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop()); setIsRecording(false);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (audioBlob.size < 1000) return;
        try {
          const reader = new FileReader();
          reader.readAsDataURL(audioBlob);
          reader.onloadend = async () => {
            const base64 = (reader.result as string).split(',')[1];
            const res = await chatApi.transcribe(base64, 'webm');
            const text = res.data.text?.trim();
            if (text) {
              try { const voiceRes = await chatApi.voiceCommand(text); if (voiceRes.data.matched) { showToast(voiceRes.data.message || '指令已执行', 'success'); return; } } catch {}
              setInputText(prev => prev + text);
            }
          };
        } catch { showToast('语音识别失败，请重试', 'error'); }
      };
      mediaRecorder.start(); setIsRecording(true);
    } catch { showToast('无法访问麦克风，请检查浏览器权限', 'warning'); }
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    e.target.value = '';
    setImageUploading(true);
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onloadend = () => {
      const dataUrl = reader.result as string;
      const base64 = dataUrl.split(',')[1];
      if (file.type.startsWith('image/')) { setImagePreview(dataUrl); setPendingImage({ base64, type: file.type.replace('image/', '') || 'jpeg' }); }
      else setPendingFile({ base64, name: file.name });
      setImageUploading(false);
    };
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items; if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        e.preventDefault();
        const file = items[i].getAsFile(); if (!file) return;
        setImageUploading(true);
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onloadend = () => { const dataUrl = reader.result as string; setImagePreview(dataUrl); setPendingImage({ base64: dataUrl.split(',')[1], type: file.type.replace('image/', '') || 'png' }); setImageUploading(false); };
        return;
      }
    }
  };

  return {
    isRecording, imageUploading, imagePreview, pendingImage, pendingFile,
    fileInputRef, clearPendingAttachment,
    handleVoiceToggle, handleImageUpload, handlePaste,
  };
}
