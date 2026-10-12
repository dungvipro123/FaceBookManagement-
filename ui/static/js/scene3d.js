import * as THREE from "../vendor/three.module.js";

let bgRenderer, bgScene, bgCamera, bgParticles;
let coreRenderer, coreScene, coreCamera, coreMesh, coreWire, coreGlow;
let currentColor = "amber";
let isBursting = false;

export function initBackground(canvas) {
    if (!canvas) return;
    try {
        bgScene = new THREE.Scene();
        bgCamera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
        bgCamera.position.z = 200;

        bgRenderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
        bgRenderer.setSize(window.innerWidth, window.innerHeight);
        bgRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));

        // Create Starfield / Particle field
        const particleCount = 400;
        const geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(particleCount * 3);

        for (let i = 0; i < particleCount * 3; i += 3) {
            positions[i] = (Math.random() - 0.5) * 600;
            positions[i + 1] = (Math.random() - 0.5) * 600;
            positions[i + 2] = (Math.random() - 0.5) * 400;
        }

        geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        const material = new THREE.PointsMaterial({
            color: 0x38BDF8,
            size: 2.2,
            transparent: true,
            opacity: 0.4
        });

        bgParticles = new THREE.Points(geometry, material);
        bgScene.add(bgParticles);

        let mouseX = 0, mouseY = 0;
        window.addEventListener("mousemove", (e) => {
            mouseX = (e.clientX - window.innerWidth / 2) * 0.05;
            mouseY = (e.clientY - window.innerHeight / 2) * 0.05;
        });

        window.addEventListener("resize", () => {
            if (!bgCamera || !bgRenderer) return;
            bgCamera.aspect = window.innerWidth / window.innerHeight;
            bgCamera.updateProjectionMatrix();
            bgRenderer.setSize(window.innerWidth, window.innerHeight);
        });

        function animateBg() {
            if (!document.hidden && bgRenderer && bgScene) {
                bgParticles.rotation.y += 0.0006;
                bgParticles.rotation.x += 0.0003;
                bgCamera.position.x += (mouseX - bgCamera.position.x) * 0.05;
                bgCamera.position.y += (-mouseY - bgCamera.position.y) * 0.05;
                bgRenderer.render(bgScene, bgCamera);
            }
            requestAnimationFrame(animateBg);
        }
        animateBg();
    } catch (e) {
        console.warn("WebGL background unavailable, skipping 3D particle field:", e);
    }
}

export function initStatusCore(canvas) {
    if (!canvas) return;
    try {
        const width = canvas.clientWidth || 240;
        const height = canvas.clientHeight || 240;

        coreScene = new THREE.Scene();
        coreCamera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
        coreCamera.position.z = 4.8;

        coreRenderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
        coreRenderer.setSize(width, height);
        coreRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

        // Core Solid Sphere
        const sphereGeo = new THREE.SphereGeometry(1.2, 32, 32);
        const sphereMat = new THREE.MeshBasicMaterial({
            color: 0xF59E0B,
            wireframe: false,
            transparent: true,
            opacity: 0.8
        });
        coreMesh = new THREE.Mesh(sphereGeo, sphereMat);
        coreScene.add(coreMesh);

        // Core Outer Wireframe Ring
        const ringGeo = new THREE.IcosahedronGeometry(1.65, 1);
        const ringMat = new THREE.MeshBasicMaterial({
            color: 0xFBBF24,
            wireframe: true,
            transparent: true,
            opacity: 0.5
        });
        coreWire = new THREE.Mesh(ringGeo, ringMat);
        coreScene.add(coreWire);

        function animateCore() {
            if (!document.hidden && coreRenderer && coreScene) {
                const time = Date.now() * 0.002;

                if (currentColor === "green") {
                    coreMesh.material.color.setHex(0x10B981);
                    coreWire.material.color.setHex(0x34D399);
                    coreMesh.rotation.y += 0.01;
                    coreWire.rotation.x += 0.012;
                    coreMesh.scale.setScalar(1.0 + Math.sin(time) * 0.04);
                } else if (currentColor === "red") {
                    coreMesh.material.color.setHex(0xEF4444);
                    coreWire.material.color.setHex(0xF87171);
                    coreMesh.rotation.y += 0.03;
                    coreWire.rotation.z += 0.04;
                    // Jitter effect
                    coreMesh.position.x = (Math.random() - 0.5) * 0.06;
                    coreMesh.position.y = (Math.random() - 0.5) * 0.06;
                } else {
                    // Amber / scanning / idle
                    coreMesh.material.color.setHex(0xF59E0B);
                    coreWire.material.color.setHex(0xFBBF24);
                    coreMesh.rotation.y += 0.015;
                    coreWire.rotation.y -= 0.01;
                    coreMesh.scale.setScalar(1.0 + Math.sin(time * 1.5) * 0.06);
                }

                if (isBursting) {
                    coreMesh.scale.setScalar(1.25);
                }

                coreRenderer.render(coreScene, coreCamera);
            }
            requestAnimationFrame(animateCore);
        }
        animateCore();
    } catch (e) {
        console.warn("WebGL core unavailable:", e);
    }
}

export function updateCoreHealth(color) {
    currentColor = color;
}

export function triggerDealBurst() {
    isBursting = true;
    setTimeout(() => {
        isBursting = false;
    }, 600);
}
