'use client';

import dynamic from 'next/dynamic';

// Dynamic import to avoid SSR issues with 3D graph
const MemoryClient = dynamic(
  () => import('@/features/memory/components/MemoryClient'),
  {
    ssr: false,
    loading: () => (
      <div className="memory-loading">
        <div className="memory-loading-spinner" />
        <p>Loading Memory UI...</p>
      </div>
    ),
  }
);

export default function MemoryPage() {
  return <MemoryClient />;
}
