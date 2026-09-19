// Models Page Component
import { useState, useEffect } from "react";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Plus, RefreshCw } from "lucide-react";
import { ModelConfig } from "@/types";
import { ModelTable } from "./ModelTable";
import { ModelForm } from "./ModelForm";
import { ModelUsageCard } from "./ModelUsageCard";
import { apiRequest } from "@/api/request";

export function ModelsPage() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingModel, setEditingModel] = useState<ModelConfig | null>(null);
  const { toast } = useToast();

  const loadModels = async () => {
    try {
      const response = await apiRequest('/api/admin/models');
      const data = await response.json();
      setModels(data.models || []);
    } catch (error) {
      toast({
        title: "Error loading models",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadModels();
  }, []);

  const handleCreate = () => {
    setEditingModel(null);
    setShowForm(true);
  };

  const handleEdit = (model: ModelConfig) => {
    setEditingModel(model);
    setShowForm(true);
  };

  const handleDelete = async (modelId: string) => {
    if (!confirm(`Are you sure you want to delete model ${modelId}?`)) return;

    try {
      const response = await apiRequest(`/api/admin/models/${modelId}`, {
        method: 'DELETE',
      });
      
      if (response.ok) {
        toast({ title: "Model deleted successfully" });
        loadModels();
      } else {
        throw new Error("Failed to delete model");
      }
    } catch (error) {
      toast({
        title: "Error deleting model",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const handleToggle = async (modelId: string, enabled: boolean) => {
    try {
      const response = await apiRequest(`/api/admin/models/${modelId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      
      if (response.ok) {
        toast({ 
          title: `Model ${enabled ? 'enabled' : 'disabled'}`,
          description: `${modelId} is now ${enabled ? 'active' : 'disabled'}`,
        });
        loadModels();
      } else {
        throw new Error("Failed to update model");
      }
    } catch (error) {
      toast({
        title: "Error updating model",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
      loadModels(); // Revert UI
    }
  };

  const handleTest = async (modelId: string) => {
    try {
      const response = await apiRequest(`/api/admin/models/${modelId}/test`, {
        method: 'POST',
      });
      
      const result = await response.json();
      
      if (response.ok) {
        toast({
          title: "Model test successful",
          description: `Response time: ${result.latency_ms?.toFixed(0) || 'N/A'}ms`,
        });
      } else {
        throw new Error(result.detail || "Test failed");
      }
    } catch (error) {
      toast({
        title: "Model test failed",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const handleSubmit = async (data: ModelConfig) => {
    try {
      const url = editingModel 
        ? `/api/admin/models/${data.id}` 
        : '/api/admin/models';
      
      const response = await apiRequest(url, {
        method: editingModel ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      
      if (response.ok) {
        toast({ 
          title: editingModel ? "Model updated" : "Model created",
        });
        setShowForm(false);
        setEditingModel(null);
        loadModels();
      } else {
        const error = await response.json();
        throw new Error(error.detail || "Operation failed");
      }
    } catch (error) {
      toast({
        title: `Error ${editingModel ? 'updating' : 'creating'} model`,
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Model Management</h1>
          <p className="text-muted-foreground">
            Configure and manage LLM models for the agent
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadModels}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button onClick={handleCreate}>
            <Plus className="mr-2 h-4 w-4" />
            Add Model
          </Button>
        </div>
      </div>

      {showForm && (
        <ModelForm
          initialData={editingModel || undefined}
          onSubmit={handleSubmit}
          onCancel={() => {
            setShowForm(false);
            setEditingModel(null);
          }}
          isEditing={!!editingModel}
        />
      )}

      <Card>
        <CardHeader>
          <CardTitle>Registered Models ({models.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <ModelTable
            models={models}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onToggle={handleToggle}
            onTest={handleTest}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {models.slice(0, 4).map((model) => (
          <ModelUsageCard
            key={model.id}
            modelId={model.id}
            displayName={model.display_name || model.id}
            provider={model.provider}
          />
        ))}
      </div>
    </div>
  );
}
