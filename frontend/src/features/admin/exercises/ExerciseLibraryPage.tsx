import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, CheckCircle2, Trash2, AlertCircle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/api/request";

interface Exercise {
  id: string;
  topic: string;
  difficulty: 'Easy' | 'Medium' | 'Hard';
  success_rate: number;
  status: 'draft' | 'validated';
}

export function ExerciseLibraryPage() {
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    fetchExercises();
  }, []);

  const fetchExercises = async () => {
    setLoading(true);
    try {
      const response = await apiRequest("/api/admin/exercises");
      if (response.ok) {
        const data = await response.json();
        setExercises(data.exercises || []);
      }
    } catch (error) {
      toast({
        title: "Erreur",
        description: "Impossible de charger la bibliothèque d'exercices",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleValidate = async (id: string) => {
    try {
      const response = await apiRequest(`/api/admin/exercises/${id}/validate`, {
        method: "POST",
      });
      if (response.ok) {
        toast({ title: "Succès", description: "Exercice validé" });
        fetchExercises();
      }
    } catch (error) {
      toast({
        title: "Erreur",
        description: "Échec de la validation",
        variant: "destructive",
      });
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Êtes-vous sûr de vouloir supprimer cet exercice ?")) return;
    try {
      const response = await apiRequest(`/api/admin/exercises/${id}`, {
        method: "DELETE",
      });
      if (response.ok) {
        toast({ title: "Supprimé", description: "L'exercice a été retiré" });
        fetchExercises();
      }
    } catch (error) {
      toast({
        title: "Erreur",
        description: "Échec de la suppression",
        variant: "destructive",
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold tracking-tight">Bibliothèque d'Exercices</h1>
        <Button onClick={() => {}}>+ Ajouter un exercice</Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Liste des Exercices</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Topic</TableHead>
                <TableHead>Difficulté</TableHead>
                <TableHead>Taux de réussite</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {exercises.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                    Aucun exercice trouvé
                  </TableCell>
                </TableRow>
              ) : (
                exercises.map((ex) => (
                  <TableRow key={ex.id}>
                    <TableCell className="font-medium">{ex.topic}</TableCell>
                    <TableCell>
                      <Badge variant={
                        ex.difficulty === 'Easy' ? 'secondary' :
                        ex.difficulty === 'Medium' ? 'default' : 'destructive'
                      }>
                        {ex.difficulty}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="w-full bg-muted h-2 rounded-full overflow-hidden max-w-[100px]">
                          <div
                            className="bg-primary h-full"
                            style={{ width: `${ex.success_rate}%` }}
                          />
                        </div>
                        <span>{ex.success_rate}%</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={ex.status === 'validated' ? 'outline' : 'secondary'}>
                        {ex.status === 'validated' ? 'Validé' : 'Brouillon'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right space-x-2">
                      {ex.status === 'draft' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleValidate(ex.id)}
                          className="text-green-600 hover:text-green-700"
                        >
                          <CheckCircle2 className="h-4 w-4 mr-1" /> Valider
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(ex.id)}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4 mr-1" /> Supprimer
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
