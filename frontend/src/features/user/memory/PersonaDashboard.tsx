import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { LoadingState } from '@/components/ui/loading-state';
import { User, Brain, Sparkles, Search, Save, Trash2, Edit2, Check, X } from 'lucide-react';
import { LearningMap } from './LearningMap';

interface PersonaDashboardProps {
  userId: string;
}

interface MemoryFact {
  id: string;
  category: string;
  content: string;
  confidence: number;
  updated_at: string;
}

interface UserProfile {
  name: string | null;
  description: string | null;
}

export function PersonaDashboard({ userId }: PersonaDashboardProps) {
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<UserProfile>({ name: '', description: '' });
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [editProfile, setEditProfile] = useState<UserProfile>({ name: '', description: '' });
  const [saveLoading, setSaveLoading] = useState(false);

  useEffect(() => {
    fetchOverview();
  }, [userId]);

  async function fetchOverview() {
    setLoading(true);
    try {
      const res = await fetch('/api/user/memory/overview');
      if (!res.ok) throw new Error('Failed to fetch overview');
      const data = await res.json();

      setProfile(data.identity);

      // Flatten facts from categories
      const allFacts: MemoryFact[] = [];
      Object.entries(data.facts_by_category).forEach(([category, factsInCategory]) => {
        (factsInCategory as MemoryFact[]).forEach(f => {
          allFacts.push({ ...f, category });
        });
      });
      setFacts(allFacts);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveProfile() {
    setSaveLoading(true);
    try {
      const res = await fetch('/api/user/memory/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editProfile),
      });
      if (!res.ok) throw new Error('Failed to save profile');
      const updated = await res.json();
      setProfile(updated);
      setIsEditing(false);
    } catch (err) {
      console.error(err);
    } finally {
      setSaveLoading(false);
    }
  }

  if (loading) return <LoadingState label="Chargement de votre cerveau..." />;

  return (
    <div className="grid gap-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-primary/10 p-2 rounded-full">
            <Brain className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Mon Cerveau</h1>
            <p className="text-sm text-muted-foreground">Identité et souvenirs cognitifs</p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Identity Card */}
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="w-4 h-4" /> Identité
            </CardTitle>
            <CardDescription>Comment l'IA me perçoit</CardDescription>
          </CardHeader>
          <CardContent>
            {!isEditing ? (
              <div className="space-y-4">
                <div>
                  <Label className="text-xs text-muted-foreground">Nom</Label>
                  <p className="text-lg font-medium">{profile.name || 'Non défini'}</p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Description</Label>
                  <p className="text-sm leading-relaxed">{profile.description || 'Aucune description disponible'}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() => {
                    setEditProfile(profile);
                    setIsEditing(true);
                  }}
                >
                  <Edit2 className="w-3 h-3 mr-2" /> Modifier
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Nom</Label>
                  <Input
                    value={editProfile.name || ''}
                    onChange={e => setEditProfile(prev => ({ ...prev, name: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Description</Label>
                  <Textarea
                    value={editProfile.description || ''}
                    onChange={e => setEditProfile(prev => ({ ...prev, description: e.target.value }))}
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    disabled={saveLoading}
                    className="flex-1"
                    onClick={handleSaveProfile}
                  >
                    {saveLoading ? '...' : <><Check className="w-3 h-3 mr-2" /> Sauvegarder</>}
                  </Button>
                  <Button
                    variant="ghost"
                    className="flex-1"
                    onClick={() => setIsEditing(false)}
                  >
                    <X className="w-3 h-3 mr-2" /> Annuler
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Learning Map Graph */}
        <div className="md:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Brain className="w-4 h-4" /> Graphe de Savoirs
              </CardTitle>
              <CardDescription>Visualisation de votre progression et dépendances</CardDescription>
            </CardHeader>
            <CardContent>
              <LearningMap userId={userId} />
            </CardContent>
          </Card>

          {/* Memory Facts Cloud */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="w-4 h-4" /> Nuage de Souvenirs
              </CardTitle>
              <CardDescription>Faits extraits de vos interactions</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {facts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Aucun fait mémorisé pour le moment.</p>
                ) : (
                  facts.map(fact => (
                    <Badge
                      key={fact.id}
                      variant="secondary"
                      className="px-3 py-1 text-xs cursor-default hover:bg-primary/10 transition-colors"
                    >
                      <span className="opacity-50 mr-1">[{fact.category}]</span>
                      {fact.content}
                    </Badge>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
