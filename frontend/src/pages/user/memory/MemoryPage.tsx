import { PersonaDashboard } from '@/features/user/memory/PersonaDashboard';
import { MemorySearchBar } from '@/features/user/memory/MemorySearchBar';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function MemoryPage() {
  // In a real app, we would get userId from useCurrentUser
  // For this implementation, we assume the context provider handles it or we pass it
  const userId = "current-user";

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
            <MemorySearchBar />
          </CardContent>
        </Card>
      </section>

      <section>
        <PersonaDashboard userId={userId} />
      </section>
    </div>
  );
}
