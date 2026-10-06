import { useState, type FormEvent } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { LoadingState } from '@/components/ui/loading-state';
import { Search, Database } from 'lucide-react';

interface MemorySearchItem {
  content: string;
  metadata: any;
  type: string;
  score: number;
}

export function MemorySearchBar() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MemorySearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch(e?: FormEvent) {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setHasSearched(true);
    try {
      const res = await fetch(`/api/user/memory/cognitive/search?query=${encodeURIComponent(query)}`);
      if (!res.ok) throw new Error('Search failed');
      const data = await res.json();
      setResults(data);
    } catch (err) {
      console.error(err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSearch} className="relative max-w-2xl mx-auto">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            className="pl-10 pr-20 h-12 text-base shadow-sm"
            placeholder="Interroger ma mémoire cognitive..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <Button
            type="submit"
            className="absolute right-1 top-1 bottom-1"
            disabled={loading || !query.trim()}
          >
            {loading ? '...' : 'Chercher'}
          </Button>
        </div>
      </form>

      {hasSearched && (
        <div className="grid gap-3 max-w-2xl mx-auto">
          {loading ? (
            <LoadingState label="Fouille du cerveau..." />
          ) : results.length > 0 ? (
            results.map((res, i) => (
              <Card key={i} className="overflow-hidden">
                <CardContent className="p-4 flex items-start gap-4">
                  <div className="bg-primary/10 p-2 rounded shrink-0">
                    <Database className="w-4 h-4 text-primary" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-medium">{res.content}</p>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground">
                        {res.type}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        Pertinence: {(res.score * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          ) : (
            <div className="text-center p-8 border-2 border-dashed rounded-lg text-muted-foreground text-sm">
              Aucun souvenir correspondant trouvé.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
