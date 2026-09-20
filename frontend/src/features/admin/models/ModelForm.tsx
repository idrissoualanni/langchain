// Model Form Component
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ModelConfig, ModelCapabilities } from "@/types";

interface ModelFormProps {
  initialData?: Partial<ModelConfig>;
  onSubmit: (data: ModelConfig) => void;
  onCancel: () => void;
  isEditing?: boolean;
}

export function ModelForm({ initialData, onSubmit, onCancel, isEditing = false }: ModelFormProps) {
  const [formData, setFormData] = useState<Partial<ModelConfig>>({
    id: '',
    display_name: '',
    provider: 'ollama',
    model_name: '',
    gateway_model: '',
    enabled: true,
    context_window: null,
    max_output_tokens: null,
    capabilities: {
      supports_tools: false,
      supports_structured_output: false,
      supports_vision: false,
      supports_audio: false,
    },
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
          <CardTitle>{isEditing ? 'Edit Model' : 'Create Model'}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="id">Model ID</Label>
              <Input
                id="id"
                value={formData.id}
                onChange={(e) => setFormData(prev => ({ ...prev, id: e.target.value }))}
                placeholder="e.g., coding-fast"
                disabled={isEditing}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="display_name">Display Name</Label>
              <Input
                id="display_name"
                value={formData.display_name}
                onChange={(e) => setFormData(prev => ({ ...prev, display_name: e.target.value }))}
                placeholder="e.g., Fast Coding Model"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="provider">Provider</Label>
              <Select
                value={formData.provider}
                onValueChange={(value) => setFormData(prev => ({ ...prev, provider: value }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select provider" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ollama">Ollama</SelectItem>
                  <SelectItem value="openai">OpenAI</SelectItem>
                  <SelectItem value="anthropic">Anthropic</SelectItem>
                  <SelectItem value="google">Google</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="model_name">Model Name</Label>
              <Input
                id="model_name"
                value={formData.model_name}
                onChange={(e) => setFormData(prev => ({ ...prev, model_name: e.target.value }))}
                placeholder="e.g., llama3.1, gpt-4"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="gateway_model">Gateway Model (optional)</Label>
            <Input
              id="gateway_model"
              value={formData.gateway_model || ''}
              onChange={(e) => setFormData(prev => ({ ...prev, gateway_model: e.target.value }))}
              placeholder="LiteLLM gateway model name"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="context_window">Context Window</Label>
              <Input
                id="context_window"
                type="number"
                value={formData.context_window || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, context_window: parseInt(e.target.value) || null }))}
                placeholder="e.g., 8192"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="max_output_tokens">Max Output Tokens</Label>
              <Input
                id="max_output_tokens"
                type="number"
                value={formData.max_output_tokens || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, max_output_tokens: parseInt(e.target.value) || null }))}
                placeholder="e.g., 2048"
              />
            </div>
          </div>

          <div className="space-y-4">
            <Label>Capabilities</Label>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center justify-between">
                <Label htmlFor="supports_tools" className="flex-1">Supports Tools</Label>
                <Switch
                  id="supports_tools"
                  checked={formData.capabilities?.supports_tools || false}
                  onCheckedChange={(checked) => updateCapability('supports_tools', checked)}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="supports_structured_output" className="flex-1">Structured Output</Label>
                <Switch
                  id="supports_structured_output"
                  checked={formData.capabilities?.supports_structured_output || false}
                  onCheckedChange={(checked) => updateCapability('supports_structured_output', checked)}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="supports_vision" className="flex-1">Vision</Label>
                <Switch
                  id="supports_vision"
                  checked={formData.capabilities?.supports_vision || false}
                  onCheckedChange={(checked) => updateCapability('supports_vision', checked)}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="supports_audio" className="flex-1">Audio</Label>
                <Switch
                  id="supports_audio"
                  checked={formData.capabilities?.supports_audio || false}
                  onCheckedChange={(checked) => updateCapability('supports_audio', checked)}
                />
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <Label htmlFor="enabled">Enabled</Label>
            <Switch
              id="enabled"
              checked={formData.enabled ?? true}
              onCheckedChange={(checked) => setFormData(prev => ({ ...prev, enabled: checked }))}
            />
          </div>

          <div className="flex justify-end space-x-2">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit">
              {isEditing ? 'Update' : 'Create'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </form>
  );
}
