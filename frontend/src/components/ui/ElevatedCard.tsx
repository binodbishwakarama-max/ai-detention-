import React from 'react';

interface ElevatedCardProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

export const ElevatedCard: React.FC<ElevatedCardProps> = ({ children, className = '', style = {} }) => {
  return (
    <div className={`elevated-card ${className}`} style={{ padding: '1.5rem', ...style }}>
      {children}
    </div>
  );
};
