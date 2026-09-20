// Knowledge Page Component
import { useState, useEffect } from "react";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Plus, RefreshCw, Book } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/shadcn-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { KnowledgeTable } from "./KnowledgeTable";
import { KnowledgeAccessPanel } from "./KnowledgeAccessPanel";
import { apiRequest } from "@/api/request";

interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
  scope: 'public' | 'private' | 'group' | 'user' | 'admin';
  group_ids?: string[];
  owner_user_id?: string;
  document_count?: number;
  enabled: boolean;
}

export function KnowledgePage() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [managingAccess, setManagingAccess] = useState<KnowledgeBase | null>(null);
  const [newKb, setNewKb] = useState({
    id: '',
    name: '',
    description: '',
    scope: 'private' as const,
    enabled: true,
  });
  const { toast } = useToast();

  const loadKnowledgeBases = async () => {
    try {
      const response = await apiRequest('/api/admin/knowledge');
      const data = await response.json();
      setKnowledgeBases(data.knowledge_bases || []);
    } catch (error) {
      toast({
        title: "Error loading knowledge bases",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKnowledgeBases();
  }, []);

  const handleCreate = async () => {
    try {
      const response = await apiRequest('/api/admin/knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newKb),
      });
      
      if (response.ok) {
        toast({ title: "Knowledge base created successfully" });
        setShowCreateDialog(false);
        setNewKb({ id: '', name: '', description: '', scope: 'private', enabled: true });
        loadKnowledgeBases();
      } else {
        const error = await response.json();
        throw new Error(error.detail || "Failed to create");
      }
    } catch (error) {
      toast({
        title: "Error creating knowledge base",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const handleDelete = async (kbId: string) => {
    if (!confirm(`Are you sure you want to delete this knowledge base?`)) return;

    try {
      const response = await apiRequest(`/api/admin/knowledge/${kbId}`, {
        method: 'DELETE',
      });
      
      if (response.ok) {
        toast({ title: "Knowledge base deleted successfully" });
        loadKnowledgeBases();
      } else {
        throw new Error("Failed to delete");
      }
    } catch (error) {
      toast({
        title: "Error deleting knowledge base",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const handleEdit = (_kb: KnowledgeBase) => {
    // Implement edit functionality
    toast({ title: "Edit functionality", description: "To be implemented" });
  };

  const handleManageAccess = (kb: KnowledgeBase) => {
    setManagingAccess(kb);
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Knowledge Management</h1>
          <p className="text-muted-foreground">
            Manage knowledge bases and access control
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadKnowledgeBases}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                Add Knowledge Base
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create Knowledge Base</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="kb-id">ID</Label>
                  <Input
                    id="kb-id"
                    value={newKb.id}
                    onChange={(e) => setNewKb(prev => ({ ...prev, id: e.target.value }))}
                    placeholder="e.g., python_beginner"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="kb-name">Name</Label>
                  <Input
                    id="kb-name"
                    value={newKb.name}
                    onChange={(e) => setNewKb(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., Python for Beginners"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="kb-description">Description</Label>
                  <Textarea
                    id="kb-description"
                    value={newKb.description}
                    onChange={(e) => setNewKb(prev => ({ ...prev, description: e.target.value }))}
                    placeholder="Describe this knowledge base..."
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="kb-scope">Default Scope</Label>
                  <Select
                    value={newKb.scope}
                    onValueChange={(value: any) => setNewKb(prev => ({ ...prev, scope: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="private">Private</SelectItem>
                      <SelectItem value="public">Public</SelectItem>
                      <SelectItem value="group">Group</SelectItem>
                      <SelectItem value="user">User</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="kb-enabled">Enabled</Label>
                  <Switch
                    id="kb-enabled"
                    checked={newKb.enabled}
                    onCheckedChange={(checked) => setNewKb(prev => ({ ...prev, enabled: checked }))}
                  />
                </div>
                <Button onClick={handleCreate} className="w-full">
                  Create
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {managingAccess && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Access Control: {managingAccess.name}</span>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setManagingAccess(null)}
              >
                Close
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <KnowledgeAccessPanel knowledgeBaseId={managingAccess.id} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Book className="h-5 w-5" />
            Knowledge Bases ({knowledgeBases.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <KnowledgeTable
            knowledgeBases={knowledgeBases}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onManageAccess={handleManageAccess}
          />
        </CardContent>
      </Card>
    </div>
  );
}
