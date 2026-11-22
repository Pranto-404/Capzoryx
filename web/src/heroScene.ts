/* The landing page's 3D "cash core": a faceted crystal with orbit rings, data packets, taka coins, a breathing
   cash-flow bar arc and a star field. Loaded lazily; pauses off-screen and in background tabs. */
import * as THREE from 'three';

type Theme='light'|'dark';
const PALETTE={
  dark:{core:0x1b6cff,edge:0x6ff7ff,glow:0x39d5ff,ring:0x7c5cff,packet:0x9ff9ff,coin:0xf5c451,bar:0x2fe0c2,star:0xbfe9ff,fog:0x070d1c},
  light:{core:0x4f7dff,edge:0x0fb5a7,glow:0x5aa8ff,ring:0x6d4cff,packet:0x0e9f95,coin:0xe0a43a,bar:0x18b39b,star:0x5068a8,fog:0xf4f7fd},
};

export type HeroScene={setTheme:(theme:Theme)=>void;dispose:()=>void};

export function mountHeroScene(host:HTMLElement,{theme,still}:{theme:Theme;still:boolean}):HeroScene{
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance'});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.75));
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.domElement.setAttribute('aria-hidden','true');
  host.appendChild(renderer.domElement);

  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(42,1,0.1,100);
  camera.position.set(0,0.4,8.6);camera.lookAt(0,-1.25,0);
  const world=new THREE.Group();
  scene.add(world);
  const disposables:{dispose:()=>void}[]=[];
  const keep=<T extends {dispose:()=>void}>(item:T)=>{disposables.push(item);return item;};

  // Light rig
  scene.add(new THREE.AmbientLight(0xffffff,0.55));
  const keyLight=new THREE.PointLight(0x66e8ff,40,30);keyLight.position.set(4,3,5);scene.add(keyLight);
  const rimLight=new THREE.PointLight(0x8b5cf6,32,30);rimLight.position.set(-5,-2,3);scene.add(rimLight);

  // Crystal core with a glowing edge cage and an inner pulse
  const coreGeometry=keep(new THREE.IcosahedronGeometry(1.25,1));
  const coreMaterial=keep(new THREE.MeshStandardMaterial({metalness:0.55,roughness:0.18,flatShading:true,transparent:true,opacity:0.92}));
  const core=new THREE.Mesh(coreGeometry,coreMaterial);
  const edgeMaterial=keep(new THREE.LineBasicMaterial({transparent:true,opacity:0.85}));
  const cage=new THREE.LineSegments(keep(new THREE.EdgesGeometry(keep(new THREE.IcosahedronGeometry(1.42,1)))),edgeMaterial);
  const pulseMaterial=keep(new THREE.MeshBasicMaterial({transparent:true,opacity:0.35,blending:THREE.AdditiveBlending,depthWrite:false}));
  const pulse=new THREE.Mesh(keep(new THREE.SphereGeometry(0.85,32,32)),pulseMaterial);
  const coreGroup=new THREE.Group();coreGroup.add(core,cage,pulse);world.add(coreGroup);

  // Orbit rings with travelling data packets
  const ringMaterial=keep(new THREE.MeshBasicMaterial({transparent:true,opacity:0.55}));
  const packetMaterial=keep(new THREE.MeshBasicMaterial({blending:THREE.AdditiveBlending}));
  const packetGeometry=keep(new THREE.SphereGeometry(0.06,12,12));
  const orbits=[{r:2.05,tilt:[1.2,0.2,0]},{r:2.5,tilt:[1.75,-0.5,0.3]},{r:2.95,tilt:[0.9,0.7,-0.2]}].map(({r,tilt},i)=>{
    const pivot=new THREE.Group();pivot.rotation.set(tilt[0],tilt[1],tilt[2]);
    pivot.add(new THREE.Mesh(keep(new THREE.TorusGeometry(r,0.009,8,180)),ringMaterial));
    const packets=Array.from({length:3+i},(_,k)=>{const m=new THREE.Mesh(packetGeometry,packetMaterial);m.userData.phase=k/(3+i)*Math.PI*2;pivot.add(m);return m;});
    world.add(pivot);
    return {pivot,packets,r,speed:0.35+i*0.12};
  });

  // Taka coins drifting around the core
  const coinMaterial=keep(new THREE.MeshStandardMaterial({metalness:0.55,roughness:0.28,emissiveIntensity:0.45}));
  const coinGeometry=keep(new THREE.CylinderGeometry(0.26,0.26,0.05,40));
  const coins=Array.from({length:6},(_,i)=>{
    const coin=new THREE.Mesh(coinGeometry,coinMaterial);
    coin.userData={angle:i/6*Math.PI*2,radius:3.4+(i%2)*0.5,height:(i%3-1)*0.9,spin:0.6+i*0.15};
    world.add(coin);return coin;
  });

  // Cash-flow bar arc beneath the core
  const barMaterial=keep(new THREE.MeshStandardMaterial({metalness:0.3,roughness:0.35,transparent:true,opacity:0.9,emissiveIntensity:0.55}));
  const barGeometry=keep(new THREE.BoxGeometry(0.22,1,0.22));barGeometry.translate(0,0.5,0);
  const bars=Array.from({length:11},(_,i)=>{
    const a=-0.9+i*0.18;
    const bar=new THREE.Mesh(barGeometry,barMaterial);
    bar.position.set(Math.sin(a)*3.1,-2.2,Math.cos(a)*1.2-0.4);
    bar.userData.seed=i*0.7;
    world.add(bar);return bar;
  });

  // Star field
  const starCount=window.innerWidth<700?500:1100;
  const positions=new Float32Array(starCount*3);
  for(let i=0;i<starCount;i++){
    const r=6+Math.random()*10,t=Math.random()*Math.PI*2,p=Math.acos(2*Math.random()-1);
    positions.set([r*Math.sin(p)*Math.cos(t),r*Math.sin(p)*Math.sin(t)*0.6,r*Math.cos(p)-4],i*3);
  }
  const starGeometry=keep(new THREE.BufferGeometry());starGeometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
  const starMaterial=keep(new THREE.PointsMaterial({size:0.045,transparent:true,opacity:0.8,depthWrite:false}));
  const stars=new THREE.Points(starGeometry,starMaterial);scene.add(stars);

  function setTheme(next:Theme){
    const c=PALETTE[next];
    coreMaterial.color.setHex(c.core);coreMaterial.emissive.setHex(c.core);coreMaterial.emissiveIntensity=next==='dark'?0.5:0.38;
    edgeMaterial.color.setHex(c.edge);pulseMaterial.color.setHex(c.glow);ringMaterial.color.setHex(c.ring);
    packetMaterial.color.setHex(c.packet);coinMaterial.color.setHex(c.coin);coinMaterial.emissive.setHex(c.coin);
    barMaterial.color.setHex(c.bar);barMaterial.emissive.setHex(c.bar);starMaterial.color.setHex(c.star);
    starMaterial.blending=pulseMaterial.blending=next==='dark'?THREE.AdditiveBlending:THREE.NormalBlending;
    starMaterial.needsUpdate=pulseMaterial.needsUpdate=true;
    scene.fog=new THREE.Fog(c.fog,9,22);
  }
  setTheme(theme);

  // Pointer parallax
  const target={x:0,y:0};
  const onPointer=(e:PointerEvent)=>{target.x=(e.clientX/window.innerWidth-0.5)*0.6;target.y=(e.clientY/window.innerHeight-0.5)*0.35;};
  window.addEventListener('pointermove',onPointer,{passive:true});

  function resize(){
    const {width,height}=host.getBoundingClientRect();
    if(!width||!height)return;
    renderer.setSize(width,height,false);
    camera.aspect=width/height;
    camera.position.z=width<520?11.2:9.8;
    camera.updateProjectionMatrix();
  }
  const sizes=new ResizeObserver(resize);sizes.observe(host);resize();

  const clock=new THREE.Clock();
  function frame(time:number){
    coreGroup.rotation.y=time*0.25;coreGroup.rotation.x=Math.sin(time*0.4)*0.25;
    cage.rotation.y=-time*0.15;
    const breath=1+Math.sin(time*2)*0.08;pulse.scale.setScalar(breath);
    pulseMaterial.opacity=0.25+Math.sin(time*2)*0.1;
    for(const o of orbits){
      o.pivot.rotation.z=time*0.08;
      for(const p of o.packets){const a=p.userData.phase+time*o.speed;p.position.set(Math.cos(a)*o.r,Math.sin(a)*o.r,0);}
    }
    for(const coin of coins){
      const d=coin.userData,a=d.angle+time*0.18;
      coin.position.set(Math.cos(a)*d.radius,d.height+Math.sin(time+d.angle)*0.25,Math.sin(a)*d.radius*0.55-0.6);
      coin.rotation.set(Math.PI/2.4,time*d.spin,0.3);
    }
    for(const bar of bars)bar.scale.y=0.3+(Math.sin(time*1.3+bar.userData.seed)+1)*0.42;
    stars.rotation.y=time*0.012;
    keyLight.position.x=Math.cos(time*0.5)*5;keyLight.position.z=Math.sin(time*0.5)*5;
    world.rotation.y+=(target.x-world.rotation.y)*0.04;
    world.rotation.x+=(target.y-world.rotation.x)*0.04;
    renderer.render(scene,camera);
  }

  let running=false,visible=true,raf=0;
  const loop=()=>{frame(clock.getElapsedTime());raf=requestAnimationFrame(loop);};
  const update=()=>{
    const should=!still&&visible&&document.visibilityState==='visible';
    if(should&&!running){running=true;clock.start();raf=requestAnimationFrame(loop);}
    if(!should&&running){running=false;cancelAnimationFrame(raf);clock.stop();}
  };
  const seen=new IntersectionObserver(([entry])=>{visible=!!entry?.isIntersecting;update();});seen.observe(host);
  document.addEventListener('visibilitychange',update);
  if(still)frame(1.2);else update();

  return {
    setTheme:(next)=>{setTheme(next);if(still)frame(1.2);},
    dispose(){
      running=false;cancelAnimationFrame(raf);
      seen.disconnect();sizes.disconnect();
      document.removeEventListener('visibilitychange',update);
      window.removeEventListener('pointermove',onPointer);
      disposables.forEach(item=>item.dispose());
      renderer.dispose();renderer.domElement.remove();
    },
  };
}
