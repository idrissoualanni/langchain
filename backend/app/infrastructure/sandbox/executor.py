"""
Sandbox sécurisé pour l'exécution de code étudiant.

Isolation:
- CPU limit
- RAM limit
- Execution timeout
- Filesystem isolation (tmp directory)
- Network disabled by default
- Process limit
- Output limit

Security:
- Pas d'accès au filesystem hôte
- Pas de shell arbitraire
- Pas de secrets/.env
- Pas de credentials
- Pas de réseau sortant
- Pas de processus persistants
"""

import os
import subprocess
import tempfile
import signal
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import time
try:
    import resource
except ImportError:  # Windows : module Unix-only, limites via subprocess timeout
    resource = None


class CodeExecutionRequest(BaseModel):
    """Requête d'exécution de code."""
    code: str = Field(..., description="Code à exécuter")
    language: str = Field(default="python", description="Langage (python, javascript, etc.)")
    input_data: Optional[str] = Field(None, description="Données d'entrée stdin")
    timeout_seconds: int = Field(default=10, ge=1, le=30, description="Timeout d'exécution")
    memory_limit_mb: int = Field(default=128, ge=32, le=512, description="Limite mémoire MB")
    cpu_limit: float = Field(default=1.0, ge=0.1, le=2.0, description="Limite CPU (cores)")


class CodeExecutionResult(BaseModel):
    """Résultat d'exécution de code."""
    success: bool = Field(..., description="Succès de l'exécution")
    exit_code: Optional[int] = Field(None, description="Code de sortie")
    stdout: str = Field(default="", description="Sortie standard")
    stderr: str = Field(default="", description="Sortie d'erreur")
    execution_time_ms: float = Field(default=0.0, description="Temps d'exécution ms")
    memory_used_mb: Optional[float] = Field(None, description="Mémoire utilisée MB")
    error_type: Optional[str] = Field(None, description="Type d'erreur (timeout, memory, etc.)")
    security_violation: bool = Field(default=False, description="Violation de sécurité détectée")
    security_details: Optional[List[str]] = Field(None, description="Détails des violations")


class SandboxConfig(BaseModel):
    """Configuration du sandbox."""
    max_timeout_seconds: int = Field(default=30, ge=5, le=60)
    max_memory_mb: int = Field(default=256, ge=64, le=1024)
    max_cpu_limit: float = Field(default=1.0, ge=0.1, le=2.0)
    max_output_size_kb: int = Field(default=1024, ge=64, le=10240)
    allowed_languages: List[str] = Field(default=["python"], description="Langages autorisés")
    network_enabled: bool = Field(default=False, description="Réseau activé (déconseillé)")
    file_system_access: bool = Field(default=False, description="Accès filesystem (déconseillé)")


class SecureSandbox:
    """Sandbox sécurisé pour l'exécution de code."""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._forbidden_patterns = [
            "__import__",
            "importlib",
            "subprocess",
            "os.system",
            "os.popen",
            "os.exec",
            "os.spawn",
            "socket",
            "urllib",
            "requests",
            "http.client",
            "ftplib",
            "smtplib",
            "telnetlib",
            "pickle",
            "marshal",
            "codeop",
            "compile",
            "eval",
            "exec",
            "open(",
            "file(",
            "/etc/",
            "/proc/",
            "/sys/",
            "~/",
            "../",
        ]
    
    def _check_security(self, code: str) -> List[str]:
        """Vérifie les violations de sécurité dans le code."""
        violations = []
        
        # Vérifier les patterns interdits
        for pattern in self._forbidden_patterns:
            if pattern in code:
                violations.append(f"Pattern interdit détecté: {pattern}")
        
        # Vérifier les imports dangereux
        lines = code.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                if any(forbidden in stripped for forbidden in ['socket', 'urllib', 'requests', 'http', 'ftp', 'smtp', 'telnet', 'subprocess', 'os']):
                    violations.append(f"Import dangereux: {stripped}")
        
        return violations
    
    def _setup_resource_limits(self, timeout: int, memory_mb: int, cpu_limit: float):
        """Configure les limites de ressources pour le processus enfant."""
        if resource is None:
            # Windows : ni rlimit ni SIGALRM ; le timeout reste assuré par
            # subprocess.communicate(timeout=...).
            return
        # Timeout
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(timeout)
        
        # Mémoire
        memory_bytes = memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except (ValueError, resource.error):
            pass  # Non supporté sur toutes les plateformes
        
        # CPU
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (int(timeout * cpu_limit), int(timeout * cpu_limit)))
        except (ValueError, resource.error):
            pass
        
        # Nombre de processus
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (50, 50))
        except (ValueError, resource.error):
            pass
        
        # Désactiver l'accès réseau (si disponible)
        # Note: Nécessite des capacités spéciales ou un environnement containerisé
    
    def _timeout_handler(self, signum, frame):
        """Gestionnaire de timeout."""
        raise TimeoutError("Exécution dépassée le temps imparti")
    
    def _truncate_output(self, output: str, max_size_kb: int) -> str:
        """Tronque la sortie si trop volumineuse."""
        max_size_bytes = max_size_kb * 1024
        if len(output.encode('utf-8')) > max_size_bytes:
            # output est déjà une string (text=True dans subprocess)
            return output[:max_size_bytes] + "\n... [SORTIE TRONQUÉE]"
        return output
    
    def execute_python(self, request: CodeExecutionRequest) -> CodeExecutionResult:
        """Exécute du code Python dans le sandbox."""
        start_time = time.time()
        
        # Vérifications de sécurité
        security_violations = self._check_security(request.code)
        if security_violations:
            return CodeExecutionResult(
                success=False,
                exit_code=-1,
                stderr="Violations de sécurité détectées:\n" + "\n".join(security_violations),
                security_violation=True,
                security_details=security_violations,
                error_type="security_violation"
            )
        
        # Validation des limites
        timeout = min(request.timeout_seconds, self.config.max_timeout_seconds)
        memory = min(request.memory_limit_mb, self.config.max_memory_mb)
        cpu = min(request.cpu_limit, self.config.max_cpu_limit)
        
        # Créer un fichier temporaire isolé
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            script_path = tmp_path / "script.py"
            
            # Écrire le code
            try:
                script_path.write_text(request.code, encoding='utf-8')
            except Exception as e:
                return CodeExecutionResult(
                    success=False,
                    exit_code=-1,
                    stderr=f"Erreur d'écriture du script: {str(e)}",
                    error_type="write_error"
                )
            
            # Préparer la commande — interpréteur résolu cross-platform.
            # Windows : `python` (le stub Microsoft Store `python3` est un
            # their trap — il échoue à l'exécution réelle) ;
            # POSIX : `python3`.
            interpreter = "python" if os.name == "nt" else "python3"
            cmd = [interpreter, "-u", str(script_path)]
            env = os.environ.copy()
            
            # Nettoyer l'environnement (pas de secrets)
            for key in list(env.keys()):
                if any(sensitive in key.lower() for sensitive in ['key', 'secret', 'token', 'password', 'api']):
                    del env[key]
            
            # Exécuter avec limites
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE if request.input_data else None,
                    cwd=tmpdir,
                    env=env,
                    # preexec_fn est UNIX-only — sur Windows, les limites
                    # sont assurées par subprocess.communicate(timeout=…).
                    preexec_fn=(
                        lambda: self._setup_resource_limits(timeout, memory, cpu)
                    ) if resource is not None else None,
                    text=True
                )
                
                # Exécuter
                stdout, stderr = process.communicate(
                    input=request.input_data,
                    timeout=timeout
                )
                
                exit_code = process.returncode
                
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return CodeExecutionResult(
                    success=False,
                    exit_code=-1,
                    stdout=self._truncate_output(stdout, self.config.max_output_size_kb),
                    stderr=self._truncate_output(stderr, self.config.max_output_size_kb) + "\nTIMEOUT: Exécution interrompue",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error_type="timeout"
                )
            except TimeoutError:
                return CodeExecutionResult(
                    success=False,
                    exit_code=-1,
                    stderr="TIMEOUT: Exécution dépassée le temps imparti",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error_type="timeout"
                )
            except MemoryError:
                return CodeExecutionResult(
                    success=False,
                    exit_code=-1,
                    stderr="MEMORY LIMIT: Mémoire maximale dépassée",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error_type="memory_limit"
                )
            except Exception as e:
                return CodeExecutionResult(
                    success=False,
                    exit_code=-1,
                    stderr=f"Erreur d'exécution: {str(e)}",
                    error_type="execution_error"
                )
        
        # Succès
        execution_time = (time.time() - start_time) * 1000
        
        return CodeExecutionResult(
            success=exit_code == 0,
            exit_code=exit_code,
            stdout=self._truncate_output(stdout, self.config.max_output_size_kb),
            stderr=self._truncate_output(stderr, self.config.max_output_size_kb),
            execution_time_ms=execution_time,
            error_type=None if exit_code == 0 else "runtime_error"
        )
    
    def execute(self, request: CodeExecutionRequest) -> CodeExecutionResult:
        """Point d'entrée unique pour l'exécution de code."""
        if request.language.lower() not in self.config.allowed_languages:
            return CodeExecutionResult(
                success=False,
                exit_code=-1,
                stderr=f"Langage non autorisé: {request.language}. Langages autorisés: {self.config.allowed_languages}",
                error_type="unsupported_language"
            )
        
        if request.language.lower() == "python":
            return self.execute_python(request)
        else:
            return CodeExecutionResult(
                success=False,
                exit_code=-1,
                stderr=f"Langage non implémenté: {request.language}",
                error_type="unsupported_language"
            )


# Instance globale configurée
_default_sandbox: Optional[SecureSandbox] = None


def get_sandbox(config: Optional[SandboxConfig] = None) -> SecureSandbox:
    """Obtient l'instance du sandbox (singleton)."""
    global _default_sandbox
    if _default_sandbox is None:
        _default_sandbox = SecureSandbox(config)
    return _default_sandbox


def execute_code(code: str, language: str = "python", **kwargs) -> CodeExecutionResult:
    """Fonction utilitaire pour exécuter du code rapidement."""
    request = CodeExecutionRequest(code=code, language=language, **kwargs)
    return get_sandbox().execute(request)


class ScanResult(BaseModel):
    """Résultat d'un scan statique de sécurité (sans exécution)."""
    security_violation: bool = Field(default=False)
    security_details: Optional[List[str]] = Field(None)


def scan_code(code: str) -> ScanResult:
    """Scan statique du code (patterns interdits + imports dangereux).

    Utilisé en amont par les subgraphs (coding) pour détecter une
    violation SANS exécuter le code — l'exécution réelle re-scanne
    (§24, défense en profondeur).
    """
    violations = get_sandbox()._check_security(code or "")
    return ScanResult(
        security_violation=bool(violations),
        security_details=violations or None,
    )
