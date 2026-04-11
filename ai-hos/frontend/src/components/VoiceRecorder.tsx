/**
 * Real-time voice recorder with WebRTC
 * Streams audio to backend WebSocket for transcription
 */
import { useState, useRef, useCallback } from 'react';
import { Mic, Square, Loader2 } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface VoiceRecorderProps {
  sessionId: string;
  onTranscript: (transcript: string) => void;
  onSoapNote: (note: any) => void;
  onStatusChange?: (status: 'idle' | 'recording' | 'processing' | 'completed' | 'error') => void;
}

export function VoiceRecorder({ 
  sessionId, 
  onTranscript, 
  onSoapNote,
  onStatusChange 
}: VoiceRecorderProps) {
  const [status, setStatus] = useState<'idle' | 'recording' | 'processing' | 'completed' | 'error'>('idle');
  const [recordingTime, setRecordingTime] = useState(0);
  const [error, setError] = useState<string | null>(null);
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const updateStatus = useCallback((newStatus: typeof status) => {
    setStatus(newStatus);
    onStatusChange?.(newStatus);
  }, [onStatusChange]);

  const startRecording = async () => {
    try {
      // Get microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        } 
      });

      // Setup WebSocket connection
      const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/${sessionId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        setError('Connection error');
        updateStatus('error');
      };

      // Setup MediaRecorder
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
          // Send to WebSocket in real-time (optional: buffer and send chunks)
          if (ws.readyState === WebSocket.OPEN) {
            event.data.arrayBuffer().then(buffer => {
              ws.send(buffer);
            });
          }
        }
      };

      mediaRecorder.start(1000); // Collect data every second
      updateStatus('recording');
      
      // Start timer
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);

    } catch (err) {
      console.error('Failed to start recording:', err);
      setError('Microphone access denied');
      updateStatus('error');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
      
      // Send end signal
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('END_RECORDING');
      }
    }

    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    updateStatus('processing');
  };

  const handleWebSocketMessage = (data: any) => {
    switch (data.type) {
      case 'transcription':
        onTranscript(data.transcript);
        break;
      case 'entities':
        console.log('Entities extracted:', data.entities);
        break;
      case 'soap_note':
        onSoapNote(data.soap_note);
        updateStatus('completed');
        wsRef.current?.close();
        break;
      case 'error':
        setError(data.message);
        updateStatus('error');
        break;
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col items-center gap-4 p-6 bg-white rounded-lg shadow-sm border">
      <div className="flex items-center gap-4">
        <button
          onClick={status === 'recording' ? stopRecording : startRecording}
          disabled={status === 'processing' || status === 'completed'}
          className={cn(
            "relative flex items-center justify-center w-16 h-16 rounded-full transition-all",
            status === 'recording' 
              ? "bg-red-500 hover:bg-red-600 animate-pulse"
              : "bg-blue-600 hover:bg-blue-700",
            (status === 'processing' || status === 'completed') && "opacity-50 cursor-not-allowed"
          )}
        >
          {status === 'recording' ? (
            <Square className="w-6 h-6 text-white" />
          ) : status === 'processing' ? (
            <Loader2 className="w-6 h-6 text-white animate-spin" />
          ) : (
            <Mic className="w-6 h-6 text-white" />
          )}
          
          {/* Recording indicator ring */}
          {status === 'recording' && (
            <span className="absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-20 animate-ping" />
          )}
        </button>

        <div className="text-left">
          <p className="text-lg font-semibold text-gray-900">
            {status === 'idle' && 'Ready to Record'}
            {status === 'recording' && `Recording... ${formatTime(recordingTime)}`}
            {status === 'processing' && 'Processing with AI...'}
            {status === 'completed' && 'Documentation Complete'}
            {status === 'error' && 'Error Occurred'}
          </p>
          <p className="text-sm text-gray-500">
            {status === 'idle' && 'Click to start voice documentation'}
            {status === 'recording' && 'Speak clearly into your microphone'}
            {status === 'processing' && 'Transcribing and generating SOAP note...'}
            {status === 'completed' && 'Review the generated note below'}
            {status === 'error' && error}
          </p>
        </div>
      </div>

      {/* Progress bar for processing */}
      {status === 'processing' && (
        <div className="w-full max-w-md">
          <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
            <div className="h-full bg-blue-600 animate-[shimmer_2s_infinite] w-1/2" />
          </div>
          <p className="text-xs text-center text-gray-500 mt-2">
            WhisperX ASR â†’ BioClinicalBERT NER â†’ Llama 3 SOAP Generation
          </p>
        </div>
      )}
    </div>
  );
}
