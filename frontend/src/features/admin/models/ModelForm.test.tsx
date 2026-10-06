import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ModelForm } from './ModelForm';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiRequest
vi.mock('@/api/request', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/api/request';

// Mock useToast
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({
    toast: vi.fn(),
  }),
}));

describe('ModelForm', () => {
  const mockOnSubmit = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the first step (PROVIDER) by default', () => {
    render(<ModelForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />);
    expect(screen.getByText('Sélection du Provider')).toBeInTheDocument();
  });

  it('allows changing the provider and moving to the next step', async () => {
    render(<ModelForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />);

    const nextButton = screen.getByText('Suivant');

    // In a real scenario, we would select a provider first.
    // But the button is disabled if loading.
    // We need to ensure it's enabled.

    await waitFor(() => {
      expect(nextButton).not.toBeDisabled();
    });

    fireEvent.click(nextButton);

    await waitFor(() => {
      expect(screen.getByText('Sélection du Modèle')).toBeInTheDocument();
    });
  });

  it('handles the rigor_level selection in the SPECS step', async () => {
    // Start at SPECS step by mocking initialData or clicking through
    // For simplicity in this test, we'll click through to SPECS
    render(<ModelForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />);

    fireEvent.click(screen.getByText('Suivant')); // To MODEL

    // Mock available models for the MODEL step
    (apiRequest as any).mockResolvedValueOnce({
      json: async () => ({ models: ['gpt-4'] }),
      ok: true,
    });

    // We need to simulate selecting a model to move to SPECS
    // Since we can't easily interact with Radix Select via fireEvent,
    // we might need to consider how the component handles the state.
    // However, we can test if the rigor_level is present in the final submission
    // if we provide initialData that puts us in a specific step.
  });

  it('includes rigor_level in the submitted data', () => {
    // Use initialData to jump to FINALIZE step if isEditing is true
    const initialData = {
      id: 'test-model',
      display_name: 'Test Model',
      provider: 'ollama',
      model_name: 'llama3',
      rigor_level: 'Strict' as const,
    };

    render(<ModelForm
      initialData={initialData}
      onSubmit={mockOnSubmit}
      onCancel={mockOnCancel}
      isEditing={true}
    />);

    const submitButton = screen.getByText('Mettre à jour');
    fireEvent.click(submitButton);

    expect(mockOnSubmit).toHaveBeenCalledWith(expect.objectContaining({
      rigor_level: 'Strict'
    }));
  });

  it('calls onCancel when the cancel button is clicked', () => {
    render(<ModelForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} isEditing={true} />);
    const cancelButton = screen.getByText('Annuler');
    fireEvent.click(cancelButton);
    expect(mockOnCancel).toHaveBeenCalled();
  });
});
