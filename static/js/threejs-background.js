/* =========================================================
 * tryontrend - Three.js Background Animation
 * Version: 1.0.0
 * Last updated: March 2025
 * ========================================================= */

// Import Three.js from CDN in your HTML:
// <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r134/three.min.js"></script>

class FashionBackground {
  constructor(container) {
    this.container = container || document.querySelector('.threejs-background');
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.className = 'threejs-background';
      document.body.appendChild(this.container);
    }

    this.width = window.innerWidth;
    this.height = window.innerHeight;
    this.mouseX = 0;
    this.mouseY = 0;

    this.init();
  }

  init() {
    // Create scene
    this.scene = new THREE.Scene();

    // Create camera
    this.camera = new THREE.PerspectiveCamera(75, this.width / this.height, 0.1, 2000);
    this.camera.position.z = 1000;

    // Create renderer
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true
    });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.container.appendChild(this.renderer.domElement);

    // Add particles
    this.createParticles();

    // Add lights
    this.addLights();

    // Set up event listeners
    this.setupEventListeners();

    // Start animation loop
    this.animate();
  }

  createParticles() {
    // Create a custom geometry for fashion-related particles
    const particleCount = 200;
    const positions = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);
    const colors = new Float32Array(particleCount * 3);

    const primaryColor = new THREE.Color('#4361ee');
    const secondaryColor = new THREE.Color('#4cc9f0');
    const accentColor = new THREE.Color('#f72585');
    const colorOptions = [primaryColor, secondaryColor, accentColor];

    for (let i = 0; i < particleCount; i++) {
      // Position
      positions[i * 3] = (Math.random() - 0.5) * 2000; // x
      positions[i * 3 + 1] = (Math.random() - 0.5) * 2000; // y
      positions[i * 3 + 2] = (Math.random() - 0.5) * 2000; // z

      // Size
      sizes[i] = Math.random() * 15 + 5;

      // Color
      const color = colorOptions[Math.floor(Math.random() * colorOptions.length)];
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    // Create shader material for particles
    const vertexShader = `
        attribute float size;
        attribute vec3 color;
        varying vec3 vColor;
        
        void main() {
          vColor = color;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (300.0 / -mvPosition.z);
          gl_Position = projectionMatrix * mvPosition;
        }
      `;

    const fragmentShader = `
        varying vec3 vColor;
        
        void main() {
          float distance = length(gl_PointCoord - vec2(0.5, 0.5));
          if (distance > 0.5) discard;
          
          // Soft, fashion-forward particle edge
          float alpha = 0.5 - distance;
          gl_FragColor = vec4(vColor, alpha);
        }
      `;

    const material = new THREE.ShaderMaterial({
      uniforms: {},
      vertexShader,
      fragmentShader,
      transparent: true,
      depthTest: false,
      blending: THREE.AdditiveBlending
    });

    // Create the particle system
    this.particles = new THREE.Points(geometry, material);
    this.scene.add(this.particles);

    // Add fancy 3D shapes to represent fashion elements
    this.createFashionShapes();
  }

  createFashionShapes() {
    const shapeCount = 5;
    this.shapes = [];

    // Create elegant shapes
    for (let i = 0; i < shapeCount; i++) {
      let geometry;
      const choice = Math.random();

      if (choice < 0.3) {
        // Torus (like a fashion ring or bracelet)
        geometry = new THREE.TorusGeometry(20 + Math.random() * 50, 5 + Math.random() * 10, 16, 50);
      } else if (choice < 0.6) {
        // Icosahedron (like a gemstone or diamond)
        geometry = new THREE.IcosahedronGeometry(30 + Math.random() * 30, 0);
      } else {
        // Custom geometry (like fabric folding)
        geometry = new THREE.OctahedronGeometry(40 + Math.random() * 20, 0);
      }

      // Create a glowing, semi-transparent material
      const materialOptions = [
        new THREE.MeshPhongMaterial({
          color: new THREE.Color('#4361ee'),
          transparent: true,
          opacity: 0.5 + Math.random() * 0.2,
          shininess: 100,
          side: THREE.DoubleSide
        }),
        new THREE.MeshPhongMaterial({
          color: new THREE.Color('#4cc9f0'),
          transparent: true,
          opacity: 0.5 + Math.random() * 0.2,
          shininess: 100,
          side: THREE.DoubleSide
        }),
        new THREE.MeshPhongMaterial({
          color: new THREE.Color('#f72585'),
          transparent: true,
          opacity: 0.5 + Math.random() * 0.2,
          shininess: 100,
          side: THREE.DoubleSide
        })
      ];

      const material = materialOptions[Math.floor(Math.random() * materialOptions.length)];
      const mesh = new THREE.Mesh(geometry, material);

      // Position the shape randomly in 3D space
      mesh.position.x = (Math.random() - 0.5) * 1500;
      mesh.position.y = (Math.random() - 0.5) * 1500;
      mesh.position.z = (Math.random() - 0.5) * 1500;

      // Random rotation
      mesh.rotation.x = Math.random() * Math.PI;
      mesh.rotation.y = Math.random() * Math.PI;
      mesh.rotation.z = Math.random() * Math.PI;

      // Random scale
      const scale = 0.5 + Math.random();
      mesh.scale.set(scale, scale, scale);

      // Save animation properties
      mesh.userData = {
        rotationSpeed: {
          x: (Math.random() - 0.5) * 0.002,
          y: (Math.random() - 0.5) * 0.002,
          z: (Math.random() - 0.5) * 0.002
        },
        floatSpeed: 0.3 + Math.random() * 0.5,
        floatDistance: 30 + Math.random() * 40,
        initialY: mesh.position.y,
        floatOffset: Math.random() * Math.PI * 2
      };

      this.shapes.push(mesh);
      this.scene.add(mesh);
    }
  }

  addLights() {
    // Add ambient light
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.3);
    this.scene.add(ambientLight);

    // Add directional light
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1, 1, 1);
    this.scene.add(directionalLight);

    // Add point lights for dramatic effect
    const colors = [0x4361ee, 0x4cc9f0, 0xf72585];

    for (let i = 0; i < 3; i++) {
      const light = new THREE.PointLight(colors[i], 1, 1000);
      light.position.set(
        (Math.random() - 0.5) * 1000,
        (Math.random() - 0.5) * 1000,
        (Math.random() - 0.5) * 1000
      );

      // Save animation properties
      light.userData = {
        initialPosition: light.position.clone(),
        time: Math.random() * 1000,
        amplitude: 200 + Math.random() * 100,
        frequency: 0.0002 + Math.random() * 0.0001
      };

      this.scene.add(light);
    }
  }

  setupEventListeners() {
    // Resize event
    window.addEventListener('resize', this.onWindowResize.bind(this));

    // Mouse move event for parallax effect
    document.addEventListener('mousemove', this.onMouseMove.bind(this));

    // Touch move event for mobile
    document.addEventListener('touchmove', this.onTouchMove.bind(this));

    // Scroll event for parallax
    window.addEventListener('scroll', this.onScroll.bind(this));
  }

  onWindowResize() {
    this.width = window.innerWidth;
    this.height = window.innerHeight;

    this.camera.aspect = this.width / this.height;
    this.camera.updateProjectionMatrix();

    this.renderer.setSize(this.width, this.height);
  }

  onMouseMove(event) {
    this.mouseX = (event.clientX - this.width / 2) * 0.1;
    this.mouseY = (event.clientY - this.height / 2) * 0.1;
  }

  onTouchMove(event) {
    if (event.touches.length === 1) {
      this.mouseX = (event.touches[0].clientX - this.width / 2) * 0.1;
      this.mouseY = (event.touches[0].clientY - this.height / 2) * 0.1;
    }
  }

  onScroll() {
    const scrollY = window.scrollY || window.pageYOffset;
    this.camera.position.y = -scrollY * 0.1;
  }

  animate() {
    requestAnimationFrame(this.animate.bind(this));

    // Rotate and move particles subtly
    if (this.particles) {
      this.particles.rotation.x += 0.0003;
      this.particles.rotation.y += 0.0005;

      // Create subtle flowing movement
      const positions = this.particles.geometry.attributes.position.array;
      const time = Date.now() * 0.0001;

      for (let i = 0; i < positions.length; i += 3) {
        // Add subtle sine wave motion to particles
        positions[i + 1] += Math.sin(time + positions[i] * 0.001) * 0.1;
      }

      this.particles.geometry.attributes.position.needsUpdate = true;
    }

    // Animate fashion shapes
    if (this.shapes) {
      const time = Date.now() * 0.001;

      this.shapes.forEach(shape => {
        // Rotation animation
        shape.rotation.x += shape.userData.rotationSpeed.x;
        shape.rotation.y += shape.userData.rotationSpeed.y;
        shape.rotation.z += shape.userData.rotationSpeed.z;

        // Floating animation
        shape.position.y = shape.userData.initialY +
          Math.sin(time * shape.userData.floatSpeed + shape.userData.floatOffset) *
          shape.userData.floatDistance;
      });
    }

    // Animate lights
    this.scene.children.forEach(child => {
      if (child instanceof THREE.PointLight && child.userData.initialPosition) {
        child.userData.time += 0.01;

        // Circular motion
        child.position.x = child.userData.initialPosition.x +
          Math.sin(child.userData.time * child.userData.frequency) * child.userData.amplitude;
        child.position.z = child.userData.initialPosition.z +
          Math.cos(child.userData.time * child.userData.frequency) * child.userData.amplitude;
      }
    });

    // Camera follows mouse with smooth damping
    this.camera.position.x += (this.mouseX - this.camera.position.x) * 0.05;
    this.camera.position.y += (-this.mouseY - this.camera.position.y) * 0.05;
    this.camera.lookAt(this.scene.position);

    this.renderer.render(this.scene, this.camera);
  }
}

// Initialize when the page loads
window.addEventListener('DOMContentLoaded', () => {
  const background = new FashionBackground();
});

// Export for module usage
if (typeof module !== 'undefined') {
  module.exports = { FashionBackground };
}