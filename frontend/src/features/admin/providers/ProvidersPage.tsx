import { useState, useEffect } from "react";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RefreshCw, Edit2, Save, X } from "lucide-react";
import { apiRequest } from "@/api/request";

interface ProviderConfig {
  id: string;
  name: string;
  base_url: string;
  api_key: string;
}

export function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingProvider, setEditingProvider] = useState<ProviderConfig | null>(null);
  const [editFormData, setEditFormData] = useState<Partial<ProviderConfig>>({});
  const { toast } = useToast();

  const loadProviders = async () => {
    setLoading(true);
    try {
      const response = await apiRequest('/api/admin/providers');
      const data = await response.json();
      setProviders(data.providers || []);
    } catch (error) {
      toast({
        title: "Erreur lors du chargement des providers",
        description: error instanceof Error ? error.message : "Erreur inconnue",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProviders();
  }, []);

  const handleEdit = (provider: ProviderConfig) => {
    setEditingProvider(provider);
    setEditFormData(provider);
  };

  const handleCancel = () => {
    setEditingProvider(null);
    setEditFormData({});
  };

  const handleSave = async () => {
    if (!editingProvider) return;

    try {
      const response = await apiRequest(`/api/admin/providers/${editingProvider.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editFormData),
      });

      if (response.ok) {
        toast({ title: "Provider mis à jour avec succès" });
        setEditingProvider(null);
        loadProviders();
      } else {
        const error = await response.json();
        throw new Error(error.detail || "Échec de la mise à jour");
      }
    } catch (error) {
      toast({
        title: "Erreur de mise à jour",
        description: error instanceof Error ? error.message : "Erreur inconnue",
        variant: "destructive",
      });
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64">Chargement des providers...</div>;
  }

  return (
    <div className="mx-auto w-full max-w-[72rem] space-y-6 p-4 sm:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Gestion des Providers</h1>
          <p className="text-muted-foreground">
            Configurez les endpoints et les clés API des fournisseurs de modèles
          </p>
        </div>
        <Button variant="outline" onClick={loadProviders}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Actualiser
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Liste des Providers</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Nom</TableHead>
                <TableHead>Base URL</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {providers.map((provider) => (
                <TableRow key={provider.id}>
                  <TableCell className="font-mono text-xs">{provider.id}</TableCell>
                  <TableCell>{provider.name}</TableCell>
                  <TableCell className="font-mono text-xs">{provider.base_url}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => handleEdit(provider)}>
                      <Edit2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {providers.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center py-4 text-muted-foreground">
                    Aucun provider configuré
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {editingProvider && (
        <Card className="border-primary/20 bg-primary/5">
          <CardHeader>
            <CardTitle>Modifier {editingProvider.name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="edit-name">Nom</Label>
                <Input
                  id="edit-name"
                  value={editFormData.name || ''}
                  onChange={(e) => setEditFormData(prev => ({ ...prev, name: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-url">Base URL</Label>
                <Input
                  id="edit-url"
                  value={editFormData.base_url || ''}
                  onChange={(e) => setEditFormData(prev => ({ ...prev, base_url: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-key">Clé API</Label>
                <Input
                  id="edit-key"
                  type="password"
                  value={editFormData.api_key || ''}
                  onChange={(e) => setEditFormData(prev => ({ ...prev, api_key: e.target.value }))}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={handleCancel}>
                <X className="mr-2 h-4 w-4" />
                Annuler
              </Button>
              <Button onClick={handleSave}>
                <Save className="mr-2 h-4 w-4" />
                Enregistrer les modifications
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
