/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: client side utilities
 */

function human_size (size) {
  // size: int (number of bytes)
  // returns a human readable string representing size
  const thr = 1024.
  const units = ['K','M','G','T','P','E','Z']
  if (size<thr) return `${size}B`
  size /= thr
  for (const u of units) {
    if (size<thr) return `${size.toFixed(2)}${u}iB`
    size /= thr
  }
  return `${size}YiB` // :-)
}

function encodeURIqs(uri,parm) {
  const q = Object.entries(parm).map((x)=>`${encodeURIComponent(x[0])}=${encodeURIComponent(x[1])}`).join('&')
  return `${uri}?${q}`
}

function addElement(container,tag,attrs) {
	const el = document.createElement(tag)
	if (attrs) { for (const [k,v] of Object.entries(attrs)) {el.setAttribute(k,v)} }
	container.appendChild(el)
	return el
}
function addJButton(container,icon,attrs) {
  const button = addElement(container,'button',attrs)
  addElement(button,'span',{class:`ui-icon ui-icon-${icon}`})
  return button
}
function setFadeout(element,options) {
  // duration: duration (sec) of the fadeout
  // after: wait time (sec) before fadeout
  // opacity: opacity of the fadeout menu
  const {duration,after,opacity} = Object.assign({duration:2.,after:1.,opacity:.5},options)
  const total = (duration+after)*1000, start = 1./(1.+duration/after)
  element.style.opacity = opacity
	element.addEventListener('mouseenter',(e)=>{
    for (const a of element.getAnimations()) { a.cancel() }
    element.style.opacity = opacity
  })
  element.addEventListener('mouseleave',(e)=>{
    element.style.opacity = 0.
    element.animate([{opacity:opacity},{opacity:opacity,offset:start},{opacity:0.}],total)
  })
  return element
}

function addVideoViewer(container,options) {
  // offset: where to start the video
  // menuFadeout: configuration of menu fadeout
  // ...: html video element attributes (must include width and src)
  const {width,menuFadeout,offset,...videoOptions} = Object.assign({width:'640px',offset:0,menuFadeout:{}},options)
  const div = addElement(container,'div',{style:`position:relative;width:${width};`})
  const video = addElement(div,'video',videoOptions)
  Object.assign(video.style,{width:'100%',':fullscreen':'width:100vw; height:100vh;'})
  const style = 'position:absolute;bottom:0;width:100%;background-color:black;opacity:0;display:flex;align-items:center;justify-content:center;margin-bottom:3px'
  const menu = addElement(setFadeout(addElement(div,'div',{style:style}),menuFadeout),'div',{style:'width:99%;max-width:960px;'})
  const menuTop = addElement(menu,'div',{style:'width:100%;display:block flex;'})
  const menuBot = addElement(menu,'div',{style:'width:100%;display:block flex;justify-content:space-between;'})
  const menuLeft = addElement(menuBot,'div',{style:'flex:1;display:flex;flex-direction:row;'})
  const menuRight = addElement(menuBot,'div',{style:'flex:1;display:flex;flex-direction:row-reverse;'})
  const ctrl = { video:video }
  {
    ctrl.timers = {}
    const addTimer = (n)=>{
      const timer = ctrl.timers[n] = addElement(menuTop,'span',{style:'font-size:x-small;font-family:monospace;color:white;'})
      addText(timer,'.')
    }
    addTimer('left')
    const progress = ctrl.progress = addElement(menuTop,'progress',{value:0.,max:1.,style:'flex:1;'})
    addTimer('right')
    progress.addEventListener('click',(e)=>{
      const rect = e.target.getBoundingClientRect()
      video.currentTime = offset + (video.duration-offset)*(e.x-rect.x)/rect.width
    })
  }
  {
    const button = ctrl.xplay = addElement(menuLeft,'button',{title:'toggle play/pause'}); addText(button,'⏵︎')
    button.addEventListener('click',(e)=>{
      if (video.paused) { video.play() } else { video.pause() }
    })
  }
  {
    const select = ctrl.pbrate = addElement(menuLeft,'select',{title:'speed rate'})
    for (const r of [.5,.75,1.,1.25,1.5,1.75,2.]) {
      select.appendChild(new Option(`${r}x`,r,undefined,(r==1.)))
    }
    select.addEventListener('change',(e)=>{video.playbackRate=e.target.value})
  }
  {
    const button = ctrl.xfullscreen = addElement(menuLeft,'button',{title:'toggle fullscreen'}); addText(button,'⛶')
    button.addEventListener('click',(e)=>{
      let inv = '0%'
      if (document.fullscreenElement) { document.exitFullscreen() }
      else { video.parentElement.requestFullscreen(); inv = '100%' }
      e.target.style.filter = `invert(${inv})`
    })
  }
  {
    const canvas = ctrl.volume = addElement(menuRight,'canvas',{width:100,height:15,title:'volume control'})
    const button = ctrl.xspeaker = addElement(menuRight,'button',{style:'border:none;'}); addText(button,'🔊')
    button.addEventListener('click',(e)=>{ video.volume = video.volume?0.:1. })
    let adjust = false
    for (const t of ['mousedown','mouseup','mouseleave','mousemove']) {
      canvas.addEventListener(t,(e)=>{
        switch (e.type) {
          case 'mousedown': adjust=true; break
          case 'mouseleave':
          case 'mouseup': adjust=false; return
          case 'mousemove': if (!adjust) return
        }
        const rect = e.target.getBoundingClientRect()
        video.volume = (e.x-rect.x)/rect.width
      })
    }
  }
  video.addEventListener('play',(e)=>{ctrl.xplay.textContent='⏸︎'})
  video.addEventListener('pause',(e)=>{ctrl.xplay.textContent='⏵'})
  const formatTime = (d) => {
    const ds = Math.trunc(d), dm = Math.trunc(ds/60), s = ds-60*dm, dh = Math.trunc(dm/60), m = dm-60*dh
    return `${String(dh)}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
  }
  video.addEventListener('timeupdate',(e)=>{
    const d = video.duration
    const v = {}
    if (d) {
      const currentTime = video.currentTime-offset, duration = d-offset
      if (currentTime<0) { video.currentTime = offset; return }
      for (const [n,t] of Object.entries({left:currentTime,right:duration-currentTime})) { v[n] = formatTime(t) }
      v.progress = currentTime/duration
    }
    else { v.left = v.right = '.'; v.progress = 0; }
    for (const [n,t] of Object.entries(ctrl.timers)) { t.innerText = v[n] }
    ctrl.progress.value = v.progress
  })
  {
    const {width:w,height:h} = ctrl.volume, ctx = ctrl.volume.getContext('2d')
    const gr = ctx.fillStyle = ctx.createLinearGradient(0,h,w,0)
    gr.addColorStop(0,'green');gr.addColorStop(.8,'green');gr.addColorStop(.85,'yellow');gr.addColorStop(.9,'orange');gr.addColorStop(1.,'red')
    ctx.strokeStyle = 'white'
    ctx.beginPath(); ctx.moveTo(0,h); ctx.lineTo(w,h); ctx.lineTo(w,0); ctx.closePath(); ctx.fill(); ctx.stroke()
    video.addEventListener('volumechange',(e)=>{
      const wr = w*e.target.volume, hr = h*e.target.volume
      ctx.clearRect(0,0,w,h)
      ctx.beginPath(); ctx.moveTo(0,h); ctx.lineTo(w,h); ctx.lineTo(w,0); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0,h); ctx.lineTo(wr,h); ctx.lineTo(wr,h-hr); ctx.closePath(); ctx.fill();
      ctrl.xspeaker.style.backgroundColor = e.target.volume?'':'red'
    })
  }
  return ctrl
}

function addDiapoViewer(container,options) {
  // menuFadeout: configuration of menu fadeout
  // src: list of urls of images
  // ...: html img element attributes (must include width but not src)
  const {width,menuFadeout,src,...diapoOptions} = Object.assign({width:'640px',menuFadeout:{},src:[]},options)
	const div = addElement(container,'div',{style:`position:relative;width:${width}`})
	const img = addElement(div,'img',{style:'width:100%;'})
  const menu = setFadeout(addElement(div,'div',{style:'position:absolute;top:0;left:0;width:100%;background-color:white;opacity:0;'}),menuFadeout)
  const ctrl = { img: img }
	let current = 0
	const display = (current_) => {
	  for (const [k,c] of [[current,''],[current_,'blue']]) ctrl.blist[k].style.backgroundColor = c
	  current = current_; img.setAttribute('src',src[current])
	}
  {
    const button = ctrl.xfullscreen = addElement(menu,'button',{title:'toggle fullscreen'}); addText(button,'⛶')
    button.addEventListener('click',(e)=>{
      let inv = '0%'
      if (document.fullscreenElement) { document.exitFullscreen() }
      else { img.parentElement.requestFullscreen(); inv = '100%' }
      e.target.style.filter = `invert(${inv})`
    })
  }
  {
    const sButton = (txt,tip,callback) => {
      const button = addElement(menu,'button',{title:tip,style:'border:none;padding:1mm;fontFamily:monospace;'})
      addText(button,txt)
      button.addEventListener('click',callback)
      return button
    }
    ctrl.bprev = sButton('◀','previous image',()=>display(current==0?src.length-1:current-1))
    ctrl.blist = src.map((a,k)=>sButton('🞔',`image ${k+1}`,()=>display(k)))
    ctrl.bnext = sButton('▶','next image',()=>display(current==src.length-1?0:current+1))
  }
	display(0)
	return ctrl
}
function addHeadMark(val,style) {
  const [div,div_] = [1,2].map(()=>document.createElement('div')); document.body.prepend(div,div_); div.innerText = val
  const style_ = {position:'fixed',left:'0',right:'0',top:'0',zIndex:'100',backgroundColor:'pink',textAlign:'center',fontSize:'x-large'}
  if (style) { Object.assign(style_,style) }
  Object.assign(div.style,style_)
  Object.assign(div_.style,{height:`${div.offsetHeight}px`})
}
function addText(container,data) {
  const text = document.createTextNode(data||' ')
  container.appendChild(text)
}
function toggle_display (el) { el.style.display = (el.style.display?'':'none') }
function unsavedConfirm () { return window.confirm('Unsaved changes will be lost. Are you sure you want to proceed ?') }
function deleteConfirm () { return window.confirm('Are you sure you want to delete this entry ?') }
function noopAlert () { window.alert('Nothing to save !') }

class AjaxError extends Error {
  name = 'ajax'
  constructor (err) {
    if (err.response) { super(`Server error ${err.response.status} ${err.response.statusText}\n${err.response.data}`) }
    else if (err.request) { super(`No response received from Server\n${err.request.url}`) }
    else { super(err.message) }
  }
}

export { human_size, encodeURIqs, addElement, addVideoViewer, addDiapoViewer, addJButton, addHeadMark, addText, toggle_display, unsavedConfirm, deleteConfirm, noopAlert, AjaxError }
