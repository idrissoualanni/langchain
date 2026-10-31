import { PersonaDashboard } from '@/features/user/memory/PersonaDashboard';
import { MemorySearchBar } from '@/features/user/memory/MemorySearchBar';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCurrentUser } from '@/hooks/useCurrentUser';

export function MemoryPage() {
  // Mission Identité : l'identité vient de la session, jamais du client.
  const { internal, loading } = useCurrentUser();
  const userId = internal?.user_id ?? '';

  if (loading || !userId) {
    return (
      <div className="max-w-6xl mx-auto p-6">
        <p className="text-muted-foreground">Chargement de la session…</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Mon Cerveau</h1>
        <p className="text-muted-foreground">
          Gérez votre identité numérique et explorez vos connaissances.
        </p>
      </div>

      <section className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Test de Mémoire Sémantique</CardTitle>
          </CardHeader>
          <CardContent>
            <MemorySearchBar userId={userId} />
          </CardContent>
        </Card>
      </section>

      <section>
        <PersonaDashboard userId={userId} />
      </section>
    </div>
  );
}
