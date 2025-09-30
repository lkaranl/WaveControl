#!/usr/bin/env python3
"""
Sistema de Analytics e Métricas para WaveControl

Coleta e exibe métricas de:
- Performance (FPS, latência, CPU, memória)
- Uso (gestos executados, sessões, tempo de uso)
- Sistema (câmera, MediaPipe, threads)
"""
import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import json
from pathlib import Path


@dataclass
class PerformanceMetrics:
    """Métricas de performance do sistema"""
    fps: float = 0.0
    avg_frame_time_ms: float = 0.0
    min_frame_time_ms: float = float('inf')
    max_frame_time_ms: float = 0.0
    processing_time_ms: float = 0.0
    queue_size: int = 0
    dropped_frames: int = 0
    total_frames: int = 0


@dataclass
class UsageMetrics:
    """Métricas de uso do sistema"""
    session_start: float = field(default_factory=time.time)
    session_duration: float = 0.0
    total_sessions: int = 0
    gestures_executed: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_gestures: int = 0
    calibration_time: float = 0.0
    
    def to_dict(self):
        return {
            'session_start': self.session_start,
            'session_duration': self.session_duration,
            'total_sessions': self.total_sessions,
            'gestures_executed': dict(self.gestures_executed),
            'total_gestures': self.total_gestures,
            'calibration_time': self.calibration_time,
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            session_start=data.get('session_start', time.time()),
            session_duration=data.get('session_duration', 0.0),
            total_sessions=data.get('total_sessions', 0),
            gestures_executed=defaultdict(int, data.get('gestures_executed', {})),
            total_gestures=data.get('total_gestures', 0),
            calibration_time=data.get('calibration_time', 0.0),
        )


class AnalyticsManager:
    """Gerenciador de analytics e métricas"""
    
    def __init__(self, enable_persistence=True):
        self.performance = PerformanceMetrics()
        self.usage = UsageMetrics()
        
        # Histórico de métricas (últimos 60 segundos)
        self.fps_history = deque(maxlen=60)
        self.frame_time_history = deque(maxlen=100)
        
        # Controle de tempo
        self._last_frame_time = None
        self._session_active = False
        
        # Thread-safe
        self._lock = threading.Lock()
        
        # Persistência
        self.enable_persistence = enable_persistence
        self.stats_file = Path.home() / ".wavecontrol" / "analytics.json"
        
        if enable_persistence:
            self._load_stats()
    
    def start_session(self):
        """Inicia uma nova sessão"""
        with self._lock:
            self._session_active = True
            self.usage.session_start = time.time()
            self.usage.total_sessions += 1
            self._last_frame_time = time.time()
    
    def end_session(self):
        """Finaliza sessão atual"""
        with self._lock:
            if self._session_active:
                self.usage.session_duration = time.time() - self.usage.session_start
                self._session_active = False
                
                if self.enable_persistence:
                    self._save_stats()
    
    def record_frame(self, processing_time_ms: Optional[float] = None):
        """Registra processamento de um frame"""
        with self._lock:
            current_time = time.time()
            self.performance.total_frames += 1
            
            # Calcula FPS
            if self._last_frame_time is not None:
                frame_time_ms = (current_time - self._last_frame_time) * 1000
                self.frame_time_history.append(frame_time_ms)
                
                # Atualiza métricas de tempo
                self.performance.min_frame_time_ms = min(
                    self.performance.min_frame_time_ms, frame_time_ms
                )
                self.performance.max_frame_time_ms = max(
                    self.performance.max_frame_time_ms, frame_time_ms
                )
                
                # Calcula FPS baseado no último segundo
                if len(self.frame_time_history) > 0:
                    avg_frame_time = sum(self.frame_time_history) / len(self.frame_time_history)
                    self.performance.avg_frame_time_ms = avg_frame_time
                    self.performance.fps = 1000.0 / avg_frame_time if avg_frame_time > 0 else 0
                    self.fps_history.append(self.performance.fps)
            
            # Tempo de processamento específico (se fornecido)
            if processing_time_ms is not None:
                self.performance.processing_time_ms = processing_time_ms
            
            self._last_frame_time = current_time
    
    def record_gesture(self, gesture_name: str):
        """Registra execução de um gesto"""
        with self._lock:
            if gesture_name != "neutral":
                self.usage.gestures_executed[gesture_name] += 1
                self.usage.total_gestures += 1
    
    def record_dropped_frame(self):
        """Registra frame descartado"""
        with self._lock:
            self.performance.dropped_frames += 1
    
    def set_queue_size(self, size: int):
        """Atualiza tamanho da fila de processamento"""
        with self._lock:
            self.performance.queue_size = size
    
    def set_calibration_time(self, duration: float):
        """Registra tempo de calibração"""
        with self._lock:
            self.usage.calibration_time = duration
    
    def get_stats_summary(self) -> Dict:
        """Retorna resumo das estatísticas"""
        with self._lock:
            current_session_duration = 0.0
            if self._session_active:
                current_session_duration = time.time() - self.usage.session_start
            
            return {
                'performance': {
                    'fps': round(self.performance.fps, 2),
                    'avg_frame_time_ms': round(self.performance.avg_frame_time_ms, 2),
                    'min_frame_time_ms': round(self.performance.min_frame_time_ms, 2),
                    'max_frame_time_ms': round(self.performance.max_frame_time_ms, 2),
                    'processing_time_ms': round(self.performance.processing_time_ms, 2),
                    'queue_size': self.performance.queue_size,
                    'dropped_frames': self.performance.dropped_frames,
                    'total_frames': self.performance.total_frames,
                    'drop_rate': round(
                        (self.performance.dropped_frames / self.performance.total_frames * 100) 
                        if self.performance.total_frames > 0 else 0, 2
                    ),
                },
                'usage': {
                    'current_session_duration': round(current_session_duration, 2),
                    'total_sessions': self.usage.total_sessions,
                    'total_gestures': self.usage.total_gestures,
                    'gestures_by_type': dict(self.usage.gestures_executed),
                    'calibration_time': round(self.usage.calibration_time, 2),
                    'avg_gestures_per_session': round(
                        self.usage.total_gestures / self.usage.total_sessions
                        if self.usage.total_sessions > 0 else 0, 2
                    ),
                }
            }
    
    def get_performance_report(self) -> str:
        """Retorna relatório formatado de performance"""
        stats = self.get_stats_summary()
        perf = stats['performance']
        
        return f"""
📊 PERFORMANCE METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FPS:              {perf['fps']:.2f} fps
  Frame Time:       {perf['avg_frame_time_ms']:.2f} ms (avg)
                    {perf['min_frame_time_ms']:.2f} ms (min)
                    {perf['max_frame_time_ms']:.2f} ms (max)
  Processing:       {perf['processing_time_ms']:.2f} ms
  Queue Size:       {perf['queue_size']} frames
  Total Frames:     {perf['total_frames']}
  Dropped Frames:   {perf['dropped_frames']} ({perf['drop_rate']:.2f}%)
"""
    
    def get_usage_report(self) -> str:
        """Retorna relatório formatado de uso"""
        stats = self.get_stats_summary()
        usage = stats['usage']
        
        gestures_str = "\n".join([
            f"    {name:8s}: {count:4d}x"
            for name, count in sorted(
                usage['gestures_by_type'].items(),
                key=lambda x: x[1],
                reverse=True
            )
        ])
        
        return f"""
📈 USAGE METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Session Duration:     {usage['current_session_duration']:.2f}s
  Total Sessions:       {usage['total_sessions']}
  Total Gestures:       {usage['total_gestures']}
  Avg Gestures/Session: {usage['avg_gestures_per_session']:.2f}
  Calibration Time:     {usage['calibration_time']:.2f}s

  Gestures Executed:
{gestures_str if gestures_str else "    Nenhum gesto executado"}
"""
    
    def print_stats(self):
        """Imprime estatísticas completas"""
        print(self.get_performance_report())
        print(self.get_usage_report())
    
    def reset_session_stats(self):
        """Reseta estatísticas da sessão atual"""
        with self._lock:
            self.performance = PerformanceMetrics()
            self.fps_history.clear()
            self.frame_time_history.clear()
            self._last_frame_time = None
    
    def _save_stats(self):
        """Salva estatísticas em arquivo"""
        try:
            self.stats_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Carrega stats existentes
            existing_data = {}
            if self.stats_file.exists():
                with open(self.stats_file, 'r') as f:
                    existing_data = json.load(f)
            
            # Atualiza totais acumulados
            existing_data['total_sessions'] = self.usage.total_sessions
            existing_data['total_gestures'] = existing_data.get('total_gestures', 0) + self.usage.total_gestures
            
            # Acumula gestos por tipo
            gestures = existing_data.get('gestures_executed', {})
            for gesture, count in self.usage.gestures_executed.items():
                gestures[gesture] = gestures.get(gesture, 0) + count
            existing_data['gestures_executed'] = gestures
            
            # Salva histórico de sessões
            sessions = existing_data.get('sessions', [])
            sessions.append({
                'start': self.usage.session_start,
                'duration': self.usage.session_duration,
                'gestures': dict(self.usage.gestures_executed),
                'total_gestures': self.usage.total_gestures,
            })
            # Mantém apenas últimas 100 sessões
            existing_data['sessions'] = sessions[-100:]
            
            with open(self.stats_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
                
        except Exception as e:
            print(f"⚠️  Erro ao salvar estatísticas: {e}")
    
    def _load_stats(self):
        """Carrega estatísticas do arquivo"""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                    self.usage.total_sessions = data.get('total_sessions', 0)
                    
        except Exception as e:
            print(f"⚠️  Erro ao carregar estatísticas: {e}")
    
    def get_historical_stats(self) -> Dict:
        """Retorna estatísticas históricas de todas as sessões"""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️  Erro ao carregar histórico: {e}")
        
        return {
            'total_sessions': 0,
            'total_gestures': 0,
            'gestures_executed': {},
            'sessions': []
        }


# Instância global (singleton)
_analytics_instance = None

def get_analytics(enable_persistence=True) -> AnalyticsManager:
    """Retorna instância global do analytics manager"""
    global _analytics_instance
    if _analytics_instance is None:
        _analytics_instance = AnalyticsManager(enable_persistence=enable_persistence)
    return _analytics_instance
