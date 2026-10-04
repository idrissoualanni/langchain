// ChunkEmbeddingViz3D — nuage 3D des chunks vectorisés ( admin ).
//
// Rendu Three.js via React Three Fiber :
//   - `Points`         : un point par chunk ( couleur par matière ) ;
//   - `Mesh`           : sphères instanciées + plan-sol ;
//   - `Line`           : arêtes kNN ( lineSegments ) + axes PCA ( axesHelper ).
//
// La réduction PCA est calculée CÔTÉ BACKEND ( numpy ) — Three.js n'a pas
// de PCA ; le composant ne positionne que les coordonnées reçues.
'use client';

import { useMemo, useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { ChunkEdge, ChunkPoint } from './useChunkViz';

const PALETTE = [
  '#60a5fa', '#f472b6', '#34d399', '#fbbf24',
  '#a78bfa', '#fb7185', '#22d3ee', '#facc15',
];

/** Normalise les coordonnées PCA dans un cube ~[-3, 3]. */
function normalize(points: ChunkPoint[]): THREE.Vector3[] {
  let max = 0;
  for (const p of points) {
    max = Math.max(max, Math.abs(p.x), Math.abs(p.y), Math.abs(p.z));
  }
  const s = max > 0 ? 3 / max : 1;
  return points.map((p) => new THREE.Vector3(p.x * s, p.y * s, p.z * s));
}

interface SceneProps {
  points: ChunkPoint[];
  edges: ChunkEdge[];
  onSelect: (index: number | null) => void;
}

function Scene({ points, edges, onSelect }: SceneProps) {
  const coords = useMemo(() => normalize(points), [points]);

  const subjects = useMemo(
    () => Array.from(new Set(points.map((p) => p.subject_id))),
    [points]
  );
  const colorOf = (sid: string) =>
    PALETTE[Math.max(0, subjects.indexOf(sid)) % PALETTE.length];

  const positions = useMemo(() => {
    const a = new Float32Array(coords.length * 3);
    coords.forEach((v, i) => {
      a[i * 3] = v.x; a[i * 3 + 1] = v.y; a[i * 3 + 2] = v.z;
    });
    return a;
  }, [coords]);

  const colors = useMemo(() => {
    const a = new Float32Array(coords.length * 3);
    points.forEach((p, i) => {
      const c = new THREE.Color(colorOf(p.subject_id));
      a[i * 3] = c.r; a[i * 3 + 1] = c.g; a[i * 3 + 2] = c.b;
    });
    return a;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, coords]);

  const edgePositions = useMemo(() => {
    const segs: number[] = [];
    for (const e of edges) {
      const a = coords[e.source];
      const b = coords[e.target];
      if (!a || !b) continue;
      segs.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
    return new Float32Array(segs);
  }, [edges, coords]);

  const spheres = useMemo(() => {
    const geo = new THREE.SphereGeometry(0.045, 10, 10);
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.5 });
    const n = Math.max(1, coords.length);
    const mesh = new THREE.InstancedMesh(geo, mat, n);
    const m = new THREE.Matrix4();
    const c = new THREE.Color();
    if (coords.length === 0) {
      m.makeScale(0, 0, 0);
      mesh.setMatrixAt(0, m);
    } else {
      coords.forEach((v, i) => {
        m.makeTranslation(v.x, v.y, v.z);
        mesh.setMatrixAt(i, m);
        mesh.setColorAt(i, c.set(colorOf(points[i].subject_id)));
      });
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    return mesh;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coords, points]);

  const meshRef = useRef<THREE.InstancedMesh | null>(null);
  meshRef.current = spheres;

  return (
    <group>
      <ambientLight intensity={0.9} />
      <directionalLight position={[5, 8, 5]} intensity={0.7} />
      <axesHelper args={[3.5]} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -3, 0]}>
        <planeGeometry args={[12, 12]} />
        <meshBasicMaterial
          color="#1e293b"
          transparent
          opacity={0.25}
          side={THREE.DoubleSide}
        />
      </mesh>

      <points>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[positions, 3]}
          />
          <bufferAttribute attach="attributes-color" args={[colors, 3]} />
        </bufferGeometry>
        <pointsMaterial size={0.07} sizeAttenuation vertexColors />
      </points>

      {edgePositions.length > 0 && (
        <lineSegments>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              args={[edgePositions, 3]}
            />
          </bufferGeometry>
          <lineBasicMaterial color="#475569" transparent opacity={0.35} />
        </lineSegments>
      )}

      <primitive
        object={spheres}
        onClick={(e: { stopPropagation: () => void; instanceId?: number }) => {
          e.stopPropagation();
          if (e.instanceId != null) onSelect(e.instanceId);
        }}
      />
    </group>
  );
}

interface Props {
  points: ChunkPoint[];
  edges: ChunkEdge[];
  dim: number;
  explainedVariance: number[];
  onSelect?: (point: ChunkPoint | null) => void;
}

export function ChunkEmbeddingViz3D({
  points,
  edges,
  dim,
  explainedVariance,
  onSelect,
}: Props) {
  const handleSelect = (index: number | null) => {
    if (index == null || !points[index]) {
      onSelect?.(null);
      return;
    }
    onSelect?.(points[index]);
  };

  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">
        {points.length} chunks · {dim} dims → PCA 3D · variance{' '}
        {explainedVariance.map((v) => `${(v * 100).toFixed(0)}%`).join(' / ')}
        {' '}· clic sur une sphère pour le détail
      </div>
      <div className="h-[520px] w-full overflow-hidden rounded-md border bg-slate-950">
        <Canvas camera={{ position: [6, 5, 6], fov: 55 }}>
          <Scene points={points} edges={edges} onSelect={handleSelect} />
          <OrbitControls enableDamping />
        </Canvas>
      </div>
    </div>
  );
}

export default ChunkEmbeddingViz3D;
