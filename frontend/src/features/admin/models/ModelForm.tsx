import { useState, useEffect } from "react";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
// Mock Alert components to avoid import errors if missing
const Alert = ({ children, variant }: { children: React.ReactNode; variant?: string }) => (
  <div className={`p-3 rounded-lg ${variant === 'destructive' ? 'bg-destructive/10 text-destructive' : 'bg-muted'}`}>
    {children}
  </div>
);
const AlertDescription = ({ children }: { children: React.ReactNode }) => <div>{children}</div>;

import { Loader2, CheckCircle2, AlertCircle, Info } from "lucide-react";
import type { ModelConfig, ModelCapabilities } from "@/types";
import { apiRequest } from "@/api/request";

interface ModelFormProps {
  initialData?: Partial<ModelConfig>;
  onSubmit: (data: ModelConfig) => void;
  onCancel: () => void;
  isEditing?: boolean;
}

type Step = 'PROVIDER' | 'MODEL' | 'SPECS' | 'FINALIZE';

export function ModelForm({ initialData, onSubmit, onCancel, isEditing = false }: ModelFormProps) {
  const [step, setStep] = useState<Step>(isEditing ? 'FINALIZE' : 'PROVIDER');
  const [loading, setLoading] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; latency?: number } | null>(null);
  const { toast } = useToast();

  const [formData, setFormData] = useState<Partial<ModelConfig>>({
    id: '',
    display_name: '',
    provider: 'ollama',
    model_name: '',
    gateway_model: '',
    enabled: true,
    rigor_level: 'Balanced',
    context_window: null,
    max_output_tokens: null,
    metadata: {},
    ...initialData,
    capabilities: {
      supports_tools: false,
      supports_structured_output: false,
      supports_vision: false,
      supports_audio: false,
      ...initialData?.capabilities,
    },
  });

  const [availableModels, setAvailableModels] = useState<string[]>([]);

  useEffect(() => {
    if (!isEditing && step === 'PROVIDER' && formData.provider) {
      fetchAvailableModels(formData.provider);
    }
  }, [formData.provider, isEditing]);

  const fetchAvailableModels = async (providerId: string) => {
    setLoading(true);
    try {
      const response = await apiRequest(`/api/admin/providers/${providerId}/available-models`);
      const data = await response.json();
      setAvailableModels(data.models || []);
    } catch (error) {
      toast({
        title: "Erreur de récupération",
        description: "Impossible de charger les modèles disponibles pour ce provider",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchModelSpecs = async (modelName: string) => {
    setLoading(true);
    try {
      const response = await apiRequest(`/api/admin/models/${modelName}/specs`);
      const specs = await response.json();
      setFormData(prev => ({
        ...prev,
        context_window: specs.context_window,
        max_output_tokens: specs.max_output_tokens,
        capabilities: {
          ...prev.capabilities,
          ...specs.capabilities,
        }
      }));
    } catch (error) {
      toast({
        title: "Info",
        description: "Impossible de récupérer les specs automatiquement, veuillez les saisir manuellement",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleTestModel = async () => {
    if (!formData.model_name) return;
    setLoading(true);
    setTestResult(null);
    try {
      const response = await apiRequest(`/api/admin/models/${formData.model_name}/test`, {
        method: 'POST',
      });
      const result = await response.json();
      if (response.ok) {
        setTestResult({
          success: true,
          message: "Test réussi !",
          latency: result.latency_ms
        });
      } else {
        setTestResult({
          success: false,
          message: result.detail || "Test échoué"
        });
      }
    } catch (error) {
      setTestResult({
        success: false,
        message: error instanceof Error ? error.message : "Erreur lors du test"
      });
    } finally {
      setLoading(false);
    }
  };

  const handleNext = () => {
    if (step === 'PROVIDER') {
      setStep('MODEL');
    } else if (step === 'MODEL') {
      if (formData.model_name) {
        fetchModelSpecs(formData.model_name);
      }
      setStep('SPECS');
    } else if (step === 'SPECS') {
      setStep('FINALIZE');
    }
  };

  const handlePrev = () => {
    if (step === 'MODEL') setStep('PROVIDER');
    else if (step === 'SPECS') setStep('MODEL');
    else if (step === 'FINALIZE') setStep('SPECS');
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData as ModelConfig);
  };

  const updateCapability = (key: keyof ModelCapabilities, value: boolean) => {
    setFormData(prev => ({
      ...prev,
      capabilities: { ...prev.capabilities!, [key]: value },
    }));
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card>
        <CardHeader>
          <CardTitle>{isEditing ? 'Modifier le Modèle' : 'Ajouter un Modèle'}</CardTitle>
          {!isEditing && (
            <div className="flex items-center gap-2 mt-2">
              {['PROVIDER', 'MODEL', 'SPECS', 'FINALIZE'].map((s, i) => (
                <div key={s} className="flex items-center">
                  <div className={`h-2 w-8 rounded-full ${step === s ? 'bg-primary' : 'bg-muted'}`} />
                  {i < 3 && <div className="w-2" />}
                </div>
              ))}
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-6">

          {step === 'PROVIDER' && (
            <div className="space-y-4 animate-in fade-in slide-in-from-right-4">
              <div className="space-y-2">
                <Label htmlFor="provider">Sélection du Provider</Label>
                <Select
                  value={formData.provider}
                  onValueChange={(value) => setFormData(prev => ({ ...prev, provider: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Choisir un fournisseur" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ollama">Ollama</SelectItem>
                    <SelectItem value="openai">OpenAI</SelectItem>
                    <SelectItem value="anthropic">Anthropic</SelectItem>
                    <SelectItem value="google">Google</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="p-3 rounded-lg bg-muted/50 flex gap-3 items-start text-sm text-muted-foreground">
                <Info className="h-4 w-4 mt-0.5 shrink-0" />
                <p>Sélectionnez le fournisseur pour charger la liste des modèles compatibles.</p>
              </div>
            </div>
          )}

          {step === 'MODEL' && (
            <div className="space-y-4 animate-in fade-in slide-in-from-right-4">
              <div className="space-y-2">
                <Label htmlFor="model_name">Sélection du Modèle</Label>
                <Select
                  value={formData.model_name}
                  onValueChange={(value) => setFormData(prev => ({ ...prev, model_name: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Choisir un modèle" />
                  </SelectTrigger>
                  <SelectContent>
                    {loading ? (
                      <div className="p-4 flex items-center justify-center">
                        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Chargement...
                      </div>
                    ) : availableModels.length > 0 ? (
                      availableModels.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)
                    ) : (
                      <div className="p-4 text-sm text-muted-foreground">Aucun modèle trouvé</div>
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleTestModel}
                  disabled={!formData.model_name || loading}
                >
                  {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Tester la connectivité
                </Button>
              </div>
              {testResult && (
                <Alert variant={testResult.success ? "default" : "destructive"}>
                  {testResult.success ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  <AlertDescription>
                    {testResult.message} {testResult.latency && ` (${testResult.latency.toFixed(0)}ms)`}
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}

          {step === 'SPECS' && (
            <div className="space-y-4 animate-in fade-in slide-in-from-right-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="context_window">Fenêtre de Contexte</Label>
                  <Input
                    id="context_window"
                    type="number"
                    value={formData.context_window || ''}
                    onChange={(e) => setFormData(prev => ({ ...prev, context_window: parseInt(e.target.value) || null }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="max_output_tokens">Max Tokens Sortie</Label>
                  <Input
                    id="max_output_tokens"
                    type="number"
                    value={formData.max_output_tokens || ''}
                    onChange={(e) => setFormData(prev => ({ ...prev, max_output_tokens: parseInt(e.target.value) || null }))}
                  />
                </div>
              </div>
              <div className="space-y-4">
                <Label>Niveau de Rigueur Pédagogique</Label>
                <Select
                  value={formData.rigor_level}
                  onValueChange={(value: 'Lax' | 'Balanced' | 'Strict') => setFormData(prev => ({ ...prev, rigor_level: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Choisir le niveau de rigueur" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Lax">Lax (Guidage maximum, tolérant)</SelectItem>
                    <SelectItem value="Balanced">Balanced (Équilibre entre aide et exigence)</SelectItem>
                    <SelectItem value="Strict">Strict (Exigences élevées, minimal d'aide)</SelectItem>
                  </SelectContent>
                </Select>
                <div className="p-3 rounded-lg bg-muted/50 flex gap-3 items-start text-sm text-muted-foreground">
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <p>
                    {formData.rigor_level === 'Lax' && "Le modèle sera très indulgent et guidera l'utilisateur pas à pas vers la solution."}
                    {formData.rigor_level === 'Balanced' && "Le modèle posera des questions pour faire réfléchir l'utilisateur avant de donner des indices."}
                    {formData.rigor_level === 'Strict' && "Le modèle sera exigeant et n'acceptera que des réponses précises et complètes."}
                  </p>
                </div>
              </div>
              <div className="space-y-4">
                <Label>Capacités</Label>
                <div className="grid grid-cols-2 gap-4">
                  {[
                    { id: 'supports_tools', label: 'Outils (Tools)' },
                    { id: 'supports_structured_output', label: 'Sortie Structurée' },
                    { id: 'supports_vision', label: 'Vision' },
                    { id: 'supports_audio', label: 'Audio' },
                  ].map((cap) => (
                    <div key={cap.id} className="flex items-center justify-between">
                      <Label htmlFor={cap.id} className="flex-1">{cap.label}</Label>
                      <Switch
                        id={cap.id}
                        checked={formData.capabilities?.[cap.id as keyof ModelCapabilities] || false}
                        onCheckedChange={(checked) => updateCapability(cap.id as keyof ModelCapabilities, checked)}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 'FINALIZE' && (
            <div className="space-y-4 animate-in fade-in slide-in-from-right-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="id">ID du Modèle (interne)</Label>
                  <Input
                    id="id"
                    value={formData.id}
                    onChange={(e) => setFormData(prev => ({ ...prev, id: e.target.value }))}
                    placeholder="ex: gpt-4o-fast"
                    disabled={isEditing}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="display_name">Nom d'affichage</Label>
                  <Input
                    id="display_name"
                    value={formData.display_name}
                    onChange={(e) => setFormData(prev => ({ ...prev, display_name: e.target.value }))}
                    placeholder="ex: GPT-4o Rapide"
                    required
                  />
                </div>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                <Label htmlFor="enabled" className="flex-1">Activer le modèle immédiatement</Label>
                <Switch
                  id="enabled"
                  checked={formData.enabled ?? true}
                  onCheckedChange={(checked) => setFormData(prev => ({ ...prev, enabled: checked }))}
                />
              </div>
            </div>
          )}

          <div className="flex justify-between pt-4 border-t">
            <Button type="button" variant="outline" onClick={isEditing ? onCancel : handlePrev} disabled={step === 'PROVIDER'}>
              {isEditing ? 'Annuler' : 'Précédent'}
            </Button>
            {step !== 'FINALIZE' ? (
              <Button type="button" onClick={handleNext} disabled={loading}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Suivant
              </Button>
            ) : (
              <Button type="submit" disabled={loading}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {isEditing ? 'Mettre à jour' : 'Enregistrer le modèle'}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </form>
  );
}
