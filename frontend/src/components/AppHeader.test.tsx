import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AppHeader } from './AppHeader';

describe('AppHeader', () => {
  it('shows and activates the prediction center route', () => {
    render(
      <MemoryRouter initialEntries={['/predictions']}>
        <AppHeader syncStatus={null} />
      </MemoryRouter>,
    );

    const link = screen.getByTitle('预测中心');
    expect(link).toHaveAttribute('href', '/predictions');
    expect(link).toHaveClass('active');
  });
});
