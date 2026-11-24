/**
 * Real-time clinical voice recorder with Web Speech API live dictation
 * and WebSocket streaming to the Clinical Documentation AI service.
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import { Mic, Square, Loader2, RotateCcw, Radio } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { CLINICAL_DOC_WS_URL } from '../services/api';
import type { SOAPNote } from '../types/clinical';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<{
    isFinal: boolean;
    0: { transcript: string };
  }>;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
}

interface VoiceRecorderProps {
  sessionId: string;
  onTranscript: (transcript: string, phiRedactions?: string[]) => void;
  onSoapNote: (note: SOAPNote) => void;
  onStatusChange?: (
    status: 'idle' | 'recording' | 'processing' | 'completed' | 'error'
  ) => void;
}

export function VoiceRecorder({
  sessionId,
  onTranscript,
  onSoapNote,
  onStatusChange,
}: VoiceRecorderProps) {
  const [status, setStatus] = useState<
    'idle' | 'recording' | 'processing' | 'completed' | 'error'
  >('idle');
  const [recordingTime, setRecordingTime] = useState(0);
  const [liveCaption, setLiveCaption] = useState('');
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const finalTranscriptRef = useRef('');

  const updateStatus = useCallback(
    (newStatus: typeof status) => {
      setStatus(newStatus);
      onStatusChange?.(newStatus);
    },
    [onStatusChange]
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      recognitionRef.current?.stop();
      wsRef.current?.close();
    };
  }, []);

  const handleWebSocketMessage = useCallback(
    (data: Record<string, unknown>) => {
      switch (data.type) {
        case 'transcription':
          onTranscript(
            String(data.transcript || ''),
            Array.isArray(data.phi_redactions)
              ? (data.phi_redactions as string[])
              : []
          );
          break;
        case 'soap_note':
          onSoapNote(data.soap_note as SOAPNote);
          updateStatus('completed');
          wsRef.current?.close();
          break;
        case 'error':
          setError(String(data.message || 'Processing failed'));
          updateStatus('error');
          break;
      }
    },
    [onTranscript, onSoapNote, updateStatus]
  );

  const startRecording = async () => {
    setError(null);
    setRecordingTime(0);
    setLiveCaption('');
    finalTranscriptRef.current = '';

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      const ws = new WebSocket(`${CLINICAL_DOC_WS_URL}/api/v1/ws/${sessionId}`);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          handleWebSocketMessage(JSON.parse(event.data));
        } catch (err) {
          console.error('Invalid WS message:', err);
        }
      };

      ws.onerror = () => {
        setError('Could not connect to Clinical Doc AI WebSocket (port 8000).');
        updateStatus('error');
      };

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';

      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
          event.data.arrayBuffer().then((buffer) => {
            if (ws.readyState === WebSocket.OPEN) ws.send(buffer);
          });
        }
      };

      // Optional live browser SpeechRecognition (Chrome / Edge)
      const SpeechRecCtor = (
        window as unknown as Record<string, new () => SpeechRecognitionLike>
      ).SpeechRecognition ||
        (window as unknown as Record<string, new () => SpeechRecognitionLike>)
          .webkitSpeechRecognition;

      if (SpeechRecCtor) {
        try {
          const recognition = new SpeechRecCtor();
          recognition.continuous = true;
          recognition.interimResults = true;
          recognition.lang = 'en-US';
          recognition.onresult = (event) => {
            let interim = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
              const seg = event.results[i][0].transcript;
              if (event.results[i].isFinal) {
                finalTranscriptRef.current = `${finalTranscriptRef.current} ${seg}`.trim();
                if (ws.readyState === WebSocket.OPEN) {
                  ws.send(JSON.stringify({ type: 'live_transcript', text: seg }));
                }
              } else {
                interim += seg;
              }
            }
            setLiveCaption(`${finalTranscriptRef.current} ${interim}`.trim());
          };
          recognition.onerror = () => {
            // Non-fatal: audio still streams over WebSocket
          };
          recognition.start();
          recognitionRef.current = recognition;
        } catch {
          recognitionRef.current = null;
        }
      }

      mediaRecorder.start(1000);
      updateStatus('recording');

      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch {
      setError(
        'Microphone access unavailable or denied. You can still type/paste a clinical note or load a sample case below.'
      );
      updateStatus('error');
    }
  };

  const stopRecording = () => {
    try {
      recognitionRef.current?.stop();
    } catch {
      // ignore
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
    }

    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    updateStatus('processing');

    setTimeout(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: 'END_RECORDING',
            transcript: finalTranscriptRef.current.trim(),
          })
        );
      }
    }, 250);
  };

  const reset = () => {
    setError(null);
    setRecordingTime(0);
    setLiveCaption('');
    finalTranscriptRef.current = '';
    updateStatus('idle');
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col gap-4 p-5 bg-white rounded-xl shadow-sm border border-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={status === 'recording' ? stopRecording : startRecording}
            disabled={status === 'processing'}
            className={cn(
              'relative flex items-center justify-center w-14 h-14 rounded-full transition-all shadow-sm',
              status === 'recording'
                ? 'bg-rose-600 hover:bg-rose-700'
                : 'bg-blue-600 hover:bg-blue-700',
              status === 'processing' && 'opacity-50 cursor-not-allowed'
            )}
            title={status === 'recording' ? 'Stop recording' : 'Start voice dictation'}
          >
            {status === 'recording' ? (
              <Square className="w-5 h-5 text-white fill-white" />
            ) : status === 'processing' ? (
              <Loader2 className="w-6 h-6 text-white animate-spin" />
            ) : (
              <Mic className="w-6 h-6 text-white" />
            )}
            {status === 'recording' && (
              <span className="absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-30 animate-ping" />
            )}
          </button>

          <div>
            <div className="flex items-center gap-2">
              <p className="text-base font-semibold text-slate-900">
                {status === 'idle' && 'Voice Dictation Ready'}
                {status === 'recording' && `Recording Encounter · ${formatTime(recordingTime)}`}
                {status === 'processing' && 'Synthesizing Clinical SOAP Note...'}
                {status === 'completed' && 'Voice Encounter Processed'}
                {status === 'error' && 'Voice Capture Notice'}
              </p>
              {status === 'recording' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-rose-100 text-rose-700">
                  <Radio className="w-3 h-3 animate-pulse" /> LIVE
                </span>
              )}
            </div>
            <p className="text-sm text-slate-500 mt-0.5">
              {status === 'idle' &&
                'Click the microphone to stream live dictation or use the clinical transcript editor below.'}
              {status === 'recording' &&
                'Speak clearly — click stop when finished to extract ICD-10/CPT/RxNorm codes and generate SOAP.'}
              {status === 'processing' &&
                'Running HIPAA PHI redaction, medical entity coding, and SOAP note generation...'}
              {status === 'completed' &&
                'SOAP note generated and saved to the encounter record.'}
              {status === 'error' && error}
            </p>
          </div>
        </div>

        {(status === 'completed' || status === 'error') && (
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Record Again
          </button>
        )}
      </div>

      {liveCaption && status === 'recording' && (
        <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-sm text-slate-700">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-1">
            Live Caption Preview
          </span>
          {liveCaption}
        </div>
      )}

      {status === 'processing' && (
        <div className="w-full">
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-blue-600 animate-shimmer w-1/2 rounded-full" />
          </div>
          <p className="text-xs text-center text-slate-500 mt-2">
            Audio Stream → HIPAA PHI Redaction → Clinical NER (ICD-10/CPT/RxNorm) → SOAP Note
          </p>
        </div>
      )}
    </div>
  );
}
