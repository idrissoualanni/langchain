// /settings/model — choix du modèle d'inférence.
//
// Sélecteur BORNÉ à GET /api/models : l'utilisateur ne peut choisir qu'un
// modèle réellement configuré (registry YAML / tags Ollama). Aucune saisie
// libre — jamais de modèle non configuré.
//
// La préférence est persistée localement (localStorage) et appliquée au
// store assistant (selectedModel) pour les prochains messages.
import { useEffect, useState } from 'react';
import { Check, Cpu, Loader2 } from 'lucide-react';
import { apiFetch } from '../../api/base';
import { useAssistantStore } from '../../assistant-ui/store';
import {
  EmptyState,
  PageHeader,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

interface ModelInfo {
  id: string;
  name: string;
  description: string;
  active: boolean;
}

interface ModelsResponse {
  models: ModelInfo[];
  active_model: string;
}

const STORAGE_KEY = 'dsh_preferred_model';

export function SettingsModelPage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [activeModel, setActiveModel] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const setStoreModel = useAssistantStore((s) => s.setModel);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiFetch<ModelsResponse>('/api/models')
      .then((res) => {
        if (!alive) return;
        setModels(res.models);
        setActiveModel(res.active_model);
        // Préférence déjà sauvegardée (localStorage) — prioritaire sur
        // le modèle actif du serveur, car c'est le choix de l'utilisateur.
        const stored =
          typeof window !== 'undefined'
            ? window.localStorage.getItem(STORAGE_KEY)
            : null;
        if (stored && res.models.some((m) => m.id === stored)) {
          setSelected(stored);
        } else {
          setSelected(res.active_model || null);
        }
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : 'Modèles indisponibles');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const choose = (id: string) => {
    if (saving) return;
    setSelected(id);
    setSaving(true);
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, id);
      }
      // Applique au store runtime pour les prochains messages.
      setStoreModel(id);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="settings · model"
        title="Modèle"
        description="Choisissez le modèle d’inférence utilisé pour vos conversations. Seuls les modèles configurés sont proposés."
      />

      <div className="max-w-2xl space-y-5 p-6">
        {loading ? (
          <Surface>
            <EmptyState icon={Cpu} title="Chargement des modèles…" />
          </Surface>
        ) : error ? (
          <Surface>
            <SurfaceBody>
              <EmptyState
                icon={Cpu}
                title="Modèles indisponibles"
                description={error}
              />
            </SurfaceBody>
          </Surface>
        ) : models.length === 0 ? (
          <Surface>
            <SurfaceBody>
              <EmptyState
                icon={Cpu}
                title="Aucun modèle configuré"
                description="Le backend ne remonte aucun modèle. Vérifiez la configuration (models.yaml / Ollama)."
              />
            </SurfaceBody>
          </Surface>
        ) : (
          <Surface>
            <SurfaceHeader>
              <SurfaceTitle>Modèles configurés</SurfaceTitle>
              <span className="font-mono text-[10px] text-muted-foreground/60">
                actif serveur : {activeModel || '—'}
              </span>
            </SurfaceHeader>
            <SurfaceBody className="space-y-1">
              {models.map((m) => {
                const isSelected = selected === m.id;
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => choose(m.id)}
                    disabled={saving}
                    className={`flex w-full items-center gap-3 rounded-[var(--radius-control)] border px-3 py-2.5 text-left transition-colors ${
                      isSelected
                        ? 'border-live/40 bg-live/5'
                        : 'border-transparent hover:bg-muted/60'
                    }`}
                  >
                    <span
                      className={`flex size-5 shrink-0 items-center justify-center rounded-full border ${
                        isSelected
                          ? 'border-live bg-live/15 text-live'
                          : 'border-border text-transparent'
                      }`}
                    >
                      <Check size={12} strokeWidth={2.4} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-xs font-medium text-foreground/90">
                        {m.name}
                      </span>
                      {m.description && (
                        <span className="block truncate font-mono text-[10px] text-muted-foreground/60">
                          {m.description}
                        </span>
                      )}
                    </span>
                    {m.active && (
                      <span className="shrink-0 rounded bg-live/12 px-1.5 py-0.5 font-mono text-[9px] text-live">
                        actif
                      </span>
                    )}
                  </button>
                );
              })}
            </SurfaceBody>
          </Surface>
        )}

        {saving && (
          <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            sauvegarde…
          </div>
        )}
      </div>
    </>
  );
}

export default SettingsModelPage;
