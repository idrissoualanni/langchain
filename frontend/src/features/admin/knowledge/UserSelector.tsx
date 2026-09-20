// User Selector Component
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X, Search } from "lucide-react";

interface UserSelectorProps {
  selectedUsers: string[];
  onChange: (users: string[]) => void;
  placeholder?: string;
}

export function UserSelector({ 
  selectedUsers, 
  onChange,
  placeholder = "Enter user ID"
}: UserSelectorProps) {
  const [inputValue, setInputValue] = useState("");

  const handleAddUser = () => {
    const userId = inputValue.trim();
    if (userId && !selectedUsers.includes(userId)) {
      onChange([...selectedUsers, userId]);
      setInputValue("");
    }
  };

  const handleRemoveUser = (userId: string) => {
    onChange(selectedUsers.filter(id => id !== userId));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddUser();
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="flex-1"
        />
        <Button 
          type="button" 
          onClick={handleAddUser}
          disabled={!inputValue.trim()}
        >
          <Search className="h-4 w-4 mr-2" />
          Add
        </Button>
      </div>

      {selectedUsers.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedUsers.map((userId) => (
            <Badge key={userId} variant="default" className="gap-1">
              {userId}
              <button
                onClick={() => handleRemoveUser(userId)}
                className="ml-1 hover:bg-white/20 rounded-full p-0.5"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
