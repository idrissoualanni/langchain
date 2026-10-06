import { render, screen } from '@testing-library/react';
import { StyledTable } from './styled-table';
import { describe, it, expect } from 'vitest';

describe('StyledTable', () => {
  const columns = [
    { header: 'Nom', accessor: 'name' },
    { header: 'Âge', accessor: 'age' },
  ];
  const data = [
    { name: 'Alice', age: 30 },
    { name: 'Bob', age: 25 },
  ];

  it('renders table headers correctly', () => {
    render(<StyledTable data={data} columns={columns} />);
    expect(screen.getByText('Nom')).toBeInTheDocument();
    expect(screen.getByText('Âge')).toBeInTheDocument();
  });

  it('renders table data correctly', () => {
    render(<StyledTable data={data} columns={columns} />);
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
  });

  it('renders empty state message when no data is provided', () => {
    render(<StyledTable data={[]} columns={columns} />);
    expect(screen.getByText('Aucune donnée disponible')).toBeInTheDocument();
  });

  it('renders empty state message when data is null', () => {
    render(<StyledTable data={null as any} columns={columns} />);
    expect(screen.getByText('Aucune donnée disponible')).toBeInTheDocument();
  });

  it('applies custom className to the container', () => {
    const customClass = 'my-table-class';
    render(<StyledTable data={data} columns={columns} className={customClass} />);
    const container = screen.getByText('Alice').closest('.my-table-class');
    expect(container).toBeInTheDocument();
  });
});
