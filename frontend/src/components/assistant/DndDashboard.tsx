'use client';

import { DndContext, closestCenter, DragEndEvent, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, arrayMove } from '@dnd-kit/sortable';
import SortableCard from '@/components/assistant/SortableCard';
import { ReactNode } from 'react';

interface DndDashboardProps {
  cardIds: string[];
  renderCard: (cardId: string) => ReactNode;
  onDragEnd: (oldIndex: number, newIndex: number) => void;
  onHideCard: (cardId: string) => void;
}

export { arrayMove };

export default function DndDashboard({ cardIds, renderCard, onDragEnd, onHideCard }: DndDashboardProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = cardIds.indexOf(String(active.id));
    const newIndex = cardIds.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;

    onDragEnd(oldIndex, newIndex);
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={cardIds} strategy={verticalListSortingStrategy}>
        <div className="space-y-3">
          {cardIds.map((cardId) => {
            const content = renderCard(cardId);
            if (!content) return null;
            return (
              <SortableCard key={cardId} id={cardId} editMode onHide={onHideCard}>
                {content}
              </SortableCard>
            );
          })}
        </div>
      </SortableContext>
    </DndContext>
  );
}
