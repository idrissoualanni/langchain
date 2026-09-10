// CreateThreadModal — création de thread pour le user courant
import { useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { Input } from '../ui/Input';
import type { Thread } from '../../types/agent';

interface CreateThreadModalProps {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string) => Promise<Thread>;
  onCreated: (thread: Thread) => void;
}

export function CreateThreadModal({
  open,
  onClose,
  onCreate,
  onCreated,
}: CreateThreadModalProps) {
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Thread | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName('');
    setCreating(false);
    setCreated(null);
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const submit = async () => {
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      const thread = await onCreate(name.trim());
      setCreated(thread);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur de création');
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title={created ? 'Thread created' : 'Create Thread'}
    >
      {created ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border border-[#22c55e]/30 bg-[#22c55e]/5 px-4 py-3">
            <CheckCircle2 size={20} className="text-[#22c55e]" />
            <div className="text-sm font-medium text-[#f5f7fa]">
              Thread créé avec succès
            </div>
          </div>
          <div className="space-y-2 rounded-lg border border-[#26323d] bg-[#18212b] p-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#94a3b8]">
                Name
              </div>
              <div className="text-sm text-[#f5f7fa]">{created.name}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#94a3b8]">
                Thread ID
              </div>
              <div className="font-mono text-xs text-[#6c63ff]">
                {created.thread_id}
              </div>
            </div>
          </div>
          <Button
            className="w-full"
            onClick={() => {
              onCreated(created);
              reset();
              onClose();
            }}
          >
            Continue
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-medium text-[#94a3b8]">
              Thread name
            </label>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
              placeholder="ex: Apprentissage Python"
            />
          </div>
          {error && (
            <div className="rounded-lg border border-[#ef4444]/30 bg-[#ef4444]/5 px-3 py-2 text-xs text-[#ef4444]">
              {error}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              onClick={submit}
              disabled={!name.trim() || creating}
            >
              {creating ? 'Creating…' : 'Create Thread'}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
