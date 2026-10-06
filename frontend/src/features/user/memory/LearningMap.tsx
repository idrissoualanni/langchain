import { useState, useEffect, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Text, Float, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
import { LoadingState } from '@/components/ui/loading-state';
import { Badge } from '@/components/ui/badge';
import { BrainCircuit } from 'lucide-react';

interface Concept {
  slug: string;
  level: number;
  updated_at: string;
}

interface Dependency {
  from: string;
  to: string;
}

interface LearningMapData {
  concepts: Concept[];
  dependencies: Dependency[];
}

interface LearningMapProps {
  userId: string;
}

// Color mapping: Red [0.0] -> Yellow [0.5] -> Green [1.0]
const getMasteryColor = (level: number) => {
  if (level < 0.5) {
    const t = level / 0.5;
    return new THREE.Color().setHSL(0.1 * t, 1, 0.5); // Red to Yellow
  } else {
    const t = (level - 0.5) / 0.5;
    return new THREE.Color().setHSL(0.1 + 0.2 * t, 1, 0.5); // Yellow to Green
  }
};

function ConceptNode({
  concept,
  position,
  onClick
}: {
  concept: Concept;
  position: [number, number, number];
  onClick: (c: Concept) => void
}) {
  const color = useMemo(() => getMasteryColor(concept.level), [concept.level]);
  const [hovered, setHovered] = useState(false);

  return (
    <group position={position}>
      <mesh
        onClick={(e) => {
          e.stopPropagation();
          onClick(concept);
        }}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <sphereGeometry args={[0.4, 32, 32]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={hovered ? 0.5 : 0.2}
          roughness={0.3}
          metalness={0.8}
        />
      </mesh>
      <Float speed={2} rotationIntensity={0.5} floatIntensity={0.5}>
        <Text
          position={[0, 0.7, 0]}
          fontSize={0.3}
          color="white"
          anchorX="center"
          anchorY="middle"
          maxWidth={2}
        >
          {concept.slug.replace(/_/g, ' ')}
        </Text>
      </Float>
    </group>
  );
}

function DependencyEdge({
  from,
  to
}: {
  from: [number, number, number];
  to: [number, number, number]
}) {
  const points = useMemo(() => [new THREE.Vector3(...from), new THREE.Vector3(...to)], [from, to]);
  const lineGeometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points]);

  return (
    <lineSegments geometry={lineGeometry}>
      <lineBasicMaterial color="#444" transparent opacity={0.4} />
    </lineSegments>
  );
}

function GraphScene({ data, onNodeClick }: { data: LearningMapData; onNodeClick: (c: Concept) => void }) {
  // Simple layout: ring distribution
  const nodePositions = useMemo(() => {
    const positions: Record<string, [number, number, number]> = {};
    const radius = 6;
    data.concepts.forEach((c, i) => {
      const angle = (i / data.concepts.length) * Math.PI * 2;
      positions[c.slug] = [
        Math.cos(angle) * radius,
        (Math.random() - 0.5) * 5,
        Math.sin(angle) * radius
      ];
    });
    return positions;
  }, [data.concepts]);

  return (
    <>
      <ambientLight intensity={0.5} />
      <pointLight position={[10, 10, 10]} intensity={1} />
      <PerspectiveCamera makeDefault position={[0, 10, 15]} />
      <OrbitControls enableDamping />

      {data.concepts.map(concept => (
        <ConceptNode
          key={concept.slug}
          concept={concept}
          position={nodePositions[concept.slug]}
          onClick={onNodeClick}
        />
      ))}

      {data.dependencies.map((dep, i) => {
        const fromPos = nodePositions[dep.from];
        const toPos = nodePositions[dep.to];
        if (!fromPos || !toPos) return null;
        return <DependencyEdge key={i} from={fromPos} to={toPos} />;
      })}
    </>
  );
}

export function LearningMap({ userId }: LearningMapProps) {
  const [data, setData] = useState<LearningMapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedConcept, setSelectedConcept] = useState<Concept | null>(null);

  useEffect(() => {
    async function fetchMap() {
      setLoading(true);
      try {
        const res = await fetch('/api/user/memory/learning-map');
        if (!res.ok) throw new Error('Failed to fetch learning map');
        const json = await res.json();
        setData(json);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchMap();
  }, [userId]);

  if (loading) return <LoadingState label="Cartographie de vos connaissances..." />;

  return (
    <div className="relative w-full h-[600px] rounded-xl overflow-hidden bg-slate-950 border border-slate-800">
      {/* Legend */}
      <div className="absolute top-4 left-4 z-10 bg-slate-900/80 p-3 rounded-lg border border-slate-700 text-xs text-slate-300 space-y-2 pointer-events-none">
        <div className="font-bold mb-1 flex items-center gap-2">
          <BrainCircuit className="w-3 h-3" /> Niveau de Maîtrise
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500" /> 0.0 - Débutant
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-yellow-500" /> 0.5 - Intermédiaire
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500" /> 1.0 - Expert
        </div>
      </div>

      {/* Node Details Overlay */}
      {selectedConcept && (
        <div className="absolute bottom-4 right-4 z-10 bg-slate-900/90 p-4 rounded-lg border border-slate-700 w-64 shadow-xl animate-in slide-in-from-bottom-4">
          <div className="flex justify-between items-start mb-2">
            <h3 className="font-bold text-slate-100 capitalize">
              {selectedConcept.slug.replace(/_/g, ' ')}
            </h3>
            <button
              onClick={() => setSelectedConcept(null)}
              className="text-slate-400 hover:text-white"
            >
              ×
            </button>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Maîtrise:</span>
              <Badge variant="outline" className="text-slate-200">
                {(selectedConcept.level * 100).toFixed(0)}%
              </Badge>
            </div>
            <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div
                className="h-full transition-all duration-500"
                style={{
                  width: `${selectedConcept.level * 100}%`,
                  backgroundColor: getMasteryColor(selectedConcept.level).getStyle()
                }}
              />
            </div>
            <p className="text-[10px] text-slate-500 italic">
              Dernière mise à jour: {new Date(selectedConcept.updated_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      )}

      {!data || data.concepts.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full text-slate-500 p-8 text-center">
          <BrainCircuit className="w-12 h-12 mb-4 opacity-20" />
          <p>Votre graphe de connaissances est encore vide.</p>
          <p className="text-sm opacity-60">Interagissez avec l'agent pour commencer à mapper vos acquis.</p>
        </div>
      ) : (
        <Canvas>
          <GraphScene
            data={data}
            onNodeClick={(concept) => setSelectedConcept(concept)}
          />
        </Canvas>
      )}
    </div>
  );
}

// Helper to get hex string from THREE.Color (simplified)
THREE.Color.prototype.getStyle = function() {
  const r = Math.round(this.r * 255).toString(16).padStart(2, '0');
  const g = Math.round(this.g * 255).toString(16).padStart(2, '0');
  const b = Math.round(this.b * 255).toString(16).padStart(2, '0');
  return `#${r}${g}${b}`;
};
