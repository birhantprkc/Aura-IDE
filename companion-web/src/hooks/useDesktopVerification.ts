import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import CompanionSocket, { socket } from '../api/socket';

type VerifyPhase = 'connecting' | 'verifying' | 'connected' | 'unavailable';

export function useDesktopVerification() {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<VerifyPhase>('connecting');
  const [error, setError] = useState('');
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const startedRef = useRef(false);

  const verify = useCallback(async () => {
    const storedRelay = CompanionSocket.getStoredRelayUrl();
    const effectiveRelay = storedRelay || (import.meta as any).env?.VITE_AURA_RELAY_WS_URL || '';
    const safeCtx = CompanionSocket.getStoredSafeContext();
    const storedDesktopId = safeCtx.desktop_id || '';

    if (!effectiveRelay || !storedDesktopId) {
      setPhase('unavailable');
      setError('No paired desktop found.');
      return;
    }

    setPhase('connecting');
    setError('');
    socket.connect(effectiveRelay);

    // Step 1: wait for welcome (skip if already connected)
    if (!socket.connected) {
      try {
        await new Promise<void>((resolve, reject) => {
          const unsub = socket.on('welcome', () => { unsub(); resolve(); });
          timeoutRef.current = setTimeout(() => { unsub(); reject(new Error('Connection timed out — relay not reachable.')); }, 10000);
        });
      } catch (e: any) {
        setPhase('unavailable');
        setError(e.message || 'Connection timed out — relay not reachable.');
        return;
      }
    }

    // Step 2: verify
    setPhase('verifying');
    try {
      await new Promise<void>((resolve, reject) => {
        let unsubAck: (() => void) | null = null;
        let unsubAuthErr: (() => void) | null = null;
        let unsubError: (() => void) | null = null;
        const cleanup = () => {
          if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = undefined; }
          unsubAck?.(); unsubAuthErr?.(); unsubError?.();
        };
        unsubAck = socket.on('companion.verify_ack', (data: any) => {
          const prev = CompanionSocket.getStoredSafeContext();
          const updated: any = { ...prev };
          if (data.payload?.desktop_name) {
            updated.desktop_name = data.payload.desktop_name;
            sessionStorage.setItem('companion_desktop_name', data.payload.desktop_name);
          }
          if (data.payload?.project_id !== undefined) updated.project_id = data.payload.project_id;
          if (data.payload?.conversation_id !== undefined) updated.conversation_id = data.payload.conversation_id;
          CompanionSocket.setStoredSafeContext(updated);
          cleanup(); resolve();
        });
        unsubAuthErr = socket.on('auth.error', () => { cleanup(); reject(new Error('auth.error')); });
        unsubError = socket.on('error', (data: any) => { cleanup(); reject(new Error(data.payload?.message || 'Desktop not reachable.')); });
        socket.send('companion.verify', {}, storedDesktopId);
        timeoutRef.current = setTimeout(() => { cleanup(); reject(new Error('Verification timed out — desktop not reachable.')); }, 10000);
      });
      setPhase('connected');
      setError('');
    } catch (e: any) {
      setPhase('unavailable');
      if (e.message === 'auth.error') {
        CompanionSocket.setStoredToken('');
        setError('Stored pairing is no longer valid. Pair again.');
        sessionStorage.removeItem('companion_desktop_id');
        sessionStorage.removeItem('companion_desktop_name');
      } else {
        setError(e.message || 'Desktop not reachable.');
      }
    }
  }, []);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    verify();
    return () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); };
  }, [verify]);

  // Post-verification listeners: catch auth.error / error while connected
  useEffect(() => {
    if (phase !== 'connected') return;
    const unsubAuthErr = socket.on('auth.error', () => {
      CompanionSocket.setStoredToken('');
      setPhase('unavailable');
      setError('Stored pairing is no longer valid. Pair again.');
      sessionStorage.removeItem('companion_desktop_id');
      sessionStorage.removeItem('companion_desktop_name');
    });
    const unsubError = socket.on('error', (data: any) => {
      setPhase('unavailable');
      setError(data.payload?.message || 'Desktop not reachable.');
    });
    return () => { unsubAuthErr(); unsubError(); };
  }, [phase]);

  const retry = useCallback(() => { startedRef.current = false; verify(); }, [verify]);
  const goToLogin = useCallback(() => {
    socket.logout();
    CompanionSocket.clearStoredState();
    sessionStorage.removeItem('companion_desktop_id');
    sessionStorage.removeItem('companion_desktop_name');
    navigate('/login', { replace: true });
  }, [navigate]);

  return { phase, error, retry, goToLogin };
}
