import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useThree } from "@react-three/fiber";
import { Edges, GizmoHelper, GizmoViewport, Grid, Html, OrbitControls } from "@react-three/drei";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const BED = { x: 220, y: 220, z: 280 };

/** Loads an STL (Z-up, mm) and converts it to three.js Y-up, centered on the bed. */
function useStlGeometry(url) {
  const [geometry, setGeometry] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!url) {
      setGeometry(null);
      return;
    }
    let cancelled = false;
    setError(null);
    new STLLoader().load(
      url,
      (g) => {
        if (cancelled) return g.dispose();
        g.rotateX(-Math.PI / 2);
        g.computeBoundingBox();
        const bb = g.boundingBox;
        g.translate(-(bb.min.x + bb.max.x) / 2, -bb.min.y, -(bb.min.z + bb.max.z) / 2);
        g.computeBoundingBox();
        setGeometry((prev) => {
          prev?.dispose();
          return g;
        });
      },
      undefined,
      () => !cancelled && setError("STL yüklenemedi")
    );
    return () => {
      cancelled = true;
    };
  }, [url]);
  return { geometry, error };
}

function PrintBed() {
  const volumeEdges = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(BED.x, BED.z, BED.y)), []);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.6, 0]} receiveShadow>
        <boxGeometry args={[BED.x + 16, BED.y + 16, 1]} />
        <meshStandardMaterial color="#171c25" roughness={0.9} />
      </mesh>
      <Grid
        args={[BED.x, BED.y]}
        position={[0, 0.02, 0]}
        cellSize={1}
        cellThickness={0.45}
        cellColor="#273041"
        sectionSize={10}
        sectionThickness={1}
        sectionColor="#3f5170"
        fadeDistance={3000}
        fadeStrength={0}
      />
      <lineSegments geometry={volumeEdges} position={[0, BED.z / 2, 0]}>
        <lineBasicMaterial color="#5b6b88" transparent opacity={0.22} />
      </lineSegments>
      <Html zIndexRange={[5, 0]} position={[BED.x / 2 + 10, 0, 0]} center className="axis-label x">X+</Html>
      <Html zIndexRange={[5, 0]} position={[0, 0, -BED.y / 2 - 10]} center className="axis-label y">Y+</Html>
      <Html zIndexRange={[5, 0]} position={[0, 0, BED.y / 2 + 12]} center className="axis-label front">ÖN · Ender 5 S1 · 220×220 mm</Html>
    </group>
  );
}

function Model({ geometry, showDims }) {
  const bb = geometry.boundingBox;
  const size = bb.getSize(new THREE.Vector3());
  const boxEdges = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(size.x, size.y, size.z)), [size.x, size.y, size.z]);
  return (
    <group>
      <mesh geometry={geometry} castShadow receiveShadow>
        <meshStandardMaterial color="#f97316" roughness={0.5} metalness={0.05} />
        <Edges threshold={28} color="#7c2d12" />
      </mesh>
      {showDims && (
        <>
          <lineSegments geometry={boxEdges} position={[0, size.y / 2, 0]}>
            <lineBasicMaterial color="#38bdf8" transparent opacity={0.6} />
          </lineSegments>
          <Html zIndexRange={[5, 0]} position={[0, 0, bb.max.z + 8]} center className="dim-label">X {size.x.toFixed(1)} mm</Html>
          <Html zIndexRange={[5, 0]} position={[bb.max.x + 8, 0, 0]} center className="dim-label">Y {size.z.toFixed(1)} mm</Html>
          <Html zIndexRange={[5, 0]} position={[bb.max.x + 4, size.y / 2, bb.max.z]} center className="dim-label">Z {size.y.toFixed(1)} mm</Html>
        </>
      )}
    </group>
  );
}

function CameraFit({ target, fitKey }) {
  const { camera, controls } = useThree();
  useEffect(() => {
    if (!controls) return;
    const center = target ? target.getCenter(new THREE.Vector3()) : new THREE.Vector3(0, 50, 0);
    const size = target ? target.getSize(new THREE.Vector3()) : new THREE.Vector3(BED.x, 100, BED.y);
    const radius = Math.max(size.length() / 2, 30);
    const dist = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.3;
    const dir = new THREE.Vector3(0.8, 0.65, 1).normalize();
    camera.position.copy(center).addScaledVector(dir, dist);
    camera.near = 0.5;
    camera.far = Math.max(dist * 20, 5000);
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }, [fitKey, controls]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export default function Viewer3D({ model, running, runningJob }) {
  const { geometry, error } = useStlGeometry(model?.url);
  const [showDims, setShowDims] = useState(true);
  const [fit, setFit] = useState({ key: 0, mode: "model" });
  const lastSize = useRef(null);

  // Refit only when a model of noticeably different size appears.
  useEffect(() => {
    if (!geometry) return;
    const s = geometry.boundingBox.getSize(new THREE.Vector3());
    const prev = lastSize.current;
    if (!prev || Math.abs(s.length() - prev.length()) / prev.length() > 0.15) {
      setFit((f) => ({ key: f.key + 1, mode: "model" }));
    }
    lastSize.current = s;
  }, [geometry]);

  const m = model?.metrics;
  const size = geometry?.boundingBox.getSize(new THREE.Vector3());
  const activeAgent = runningJob && Object.entries(runningJob.agents).find(([, a]) => a.status === "running");

  return (
    <main className="viewer">
      <Canvas shadows camera={{ position: [260, 230, 300], fov: 40, near: 0.5, far: 5000 }}>
        <color attach="background" args={["#0d1015"]} />
        <hemisphereLight args={["#dbe7ff", "#1b1f27", 0.7]} />
        <ambientLight intensity={0.25} />
        <directionalLight
          position={[160, 320, 200]}
          intensity={2.2}
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-camera-left={-200}
          shadow-camera-right={200}
          shadow-camera-top={200}
          shadow-camera-bottom={-200}
          shadow-camera-far={1000}
        />
        <directionalLight position={[-200, 120, -150]} intensity={0.6} />
        <PrintBed />
        {geometry && <Model geometry={geometry} showDims={showDims} />}
        <OrbitControls makeDefault enableDamping dampingFactor={0.12} maxPolarAngle={Math.PI * 0.98} />
        <CameraFit target={fit.mode === "model" && geometry ? geometry.boundingBox : null} fitKey={fit.key} />
        <GizmoHelper alignment="bottom-right" margin={[70, 70]}>
          <GizmoViewport axisColors={["#f87171", "#4ade80", "#60a5fa"]} labelColor="#0d1015" />
        </GizmoHelper>
      </Canvas>

      <div className="viewer-top-left">
        <div className="viewer-title">{model?.title || "3D Önizleme"}</div>
        {model && (
          <span className={`chip-status ${model.live ? "live" : model.result?.approved ? "ok" : "warn"}`}>
            {model.live ? "● Canlı önizleme (ajanlar çalışıyor)" : model.result?.approved ? "✓ Onaylandı" : "Kısmi onay"}
          </span>
        )}
      </div>

      <div className="viewer-toolbar">
        <button className="ghost-btn" onClick={() => setFit((f) => ({ key: f.key + 1, mode: "model" }))} disabled={!geometry}>
          Modele odaklan
        </button>
        <button className="ghost-btn" onClick={() => setFit((f) => ({ key: f.key + 1, mode: "bed" }))}>
          Tablayı göster
        </button>
        <button className={`ghost-btn ${showDims ? "on" : ""}`} onClick={() => setShowDims((v) => !v)}>
          Ölçüler
        </button>
        {model?.downloadUrl ? (
          <a className="primary-btn" href={model.downloadUrl} download>⬇ STL İndir</a>
        ) : (
          <button className="primary-btn" disabled title={running ? "Ajanlar çalışıyor…" : "Önce bir model oluşturun"}>
            ⬇ STL İndir
          </button>
        )}
      </div>

      {size && (
        <div className="viewer-metrics">
          <div className="dims">
            <span><i className="ax x">X</i>{size.x.toFixed(1)} mm</span>
            <span><i className="ax y">Y</i>{size.z.toFixed(1)} mm</span>
            <span><i className="ax z">Z</i>{size.y.toFixed(1)} mm</span>
          </div>
          {m && (
            <div className="extra">
              {m.volume_cm3 != null && <span>Hacim {m.volume_cm3} cm³</span>}
              {m.est_pla_grams_20pct != null && <span>≈{m.est_pla_grams_20pct} g PLA (%20 dolgu)</span>}
              <span>Tabla teması {m.bed_contact_mm2} mm²</span>
              <span>&gt;45° çıkıntı %{m.overhang_percent}</span>
              {m.wall?.available && <span>Min. duvar ≈{m.wall.min_mm.toFixed(1)} mm</span>}
              <span>{m.triangles?.toLocaleString("tr-TR")} üçgen</span>
            </div>
          )}
        </div>
      )}

      {!model && (
        <div className="viewer-empty">
          {running ? (
            <>
              <span className="spinner" />
              <p>{activeAgent ? runningJob.agents[activeAgent[0]].message : "Ajanlar çalışıyor…"}</p>
              <small>İlk geçerli STL üretildiğinde burada canlı görünecek.</small>
            </>
          ) : (
            <>
              <p>Henüz model yok</p>
              <small>Soldan bir fikir yazın; model Ender 5 S1 tablasında burada belirecek.</small>
            </>
          )}
        </div>
      )}
      {error && <div className="viewer-empty"><p>{error}</p></div>}
    </main>
  );
}
