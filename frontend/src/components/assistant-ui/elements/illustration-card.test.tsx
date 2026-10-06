import { render, screen } from '@testing-library/react';
import { IllustrationCard } from './illustration-card';
import { describe, it, expect } from 'vitest';

describe('IllustrationCard', () => {
  it('renders the title when provided', () => {
    render(
      <IllustrationCard id="1" type="image" title="Test Illustration">
        <div>Content</div>
      </IllustrationCard>
    );
    expect(screen.getByText('Test Illustration')).toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('does not render the title when not provided', () => {
    render(
      <IllustrationCard id="1" type="image">
        <div>Content</div>
      </IllustrationCard>
    );
    expect(screen.queryByText('Test Illustration')).not.toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('applies the custom className', () => {
    const customClass = 'my-custom-class';
    render(
      <IllustrationCard id="1" type="image" className={customClass}>
        <div>Content</div>
      </IllustrationCard>
    );
    const container = screen.getByText('Content').closest('div').parentElement?.parentElement;
    expect(container).toHaveClass(customClass);
  });
});
