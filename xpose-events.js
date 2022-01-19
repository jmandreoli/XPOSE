class XposeCalendar {

  constructor (el,cal,xpose) {
    // el: element in the page
    // cal: argument to FullCalendar.Calendar; can only specify sources (if any) through eventSources
    // xpose: object with fields id,url,sources
    el.innerHTML = ''

    var table = document.createElement('table')
    el.appendChild(table)
    var header = table.insertRow()
    header.style.fontSize = 'x-small'

    var evSource = {id:xpose.id,events:(x,success,failure)=>{return this.events(x,success,failure)}}
    if (cal.eventSources) {cal.eventSources.push(evSource)}
    else {cal.eventSources = [evSource]}
    var divCal = document.createElement('div')
    divCal.className = 'xposecalendar'
    el.appendChild(divCal)

    this.el_details = document.createElement('table')
    this.el_details.className = 'xposedetails'
    el.appendChild(this.el_details)

    header.innerHTML = '<span>Jump to:</span>'

    var navigation = document.createElement('input')
    header.insertCell().appendChild(navigation)
    navigation.style.fontSize = 'x-small'
    navigation.type = 'date'
    navigation.addEventListener('blur',()=>{navigation.value=''},false)
    navigation.addEventListener('focus',()=>{navigation.value=moment(calendar.view.currentStart).format('YYYY-MM-DD')},false)
    navigation.addEventListener('change',()=>{if(navigation.checkValidity()&&navigation.value){calendar.gotoDate(navigation.value)}},false)

    header.insertCell().innerHTML = 'Sources:'
    var sources = []
    this.sourceMap = {}
    Object.values(xpose.sources).forEach((src)=>{
      sources.push(`'${src.id}'`)
      this.sourceMap[src.id] = src
      var td = header.insertCell(); td.innerHTML = src.id
      td.style.backgroundColor = src.options.backgroundColor||'black'
      td.style.color = src.options.textColor||'white'
    })
    this.sources = sources.join(',')

    header.insertCell().innerHTML = xpose.header

    this.url = new URL(xpose.url,location.href).href
    var sql = `SELECT min(start) as low,max(start) as high FROM Event WHERE source IN (${this.sources})`
    jQuery.ajax({
      url:this.url,data:{sql:sql},
      success:(data)=>{
        data = data[0]
        var low = new Date(data.low); low.setMonth(0); low.setDate(1)
        var high = new Date(data.high); high.setFullYear(high.getFullYear()+1); high.setMonth(11); high.setDate(31)
        navigation.min = low.toISOString().substring(0,10)
        navigation.max = high.toISOString().substring(0,10)
        navigation.insertAdjacentHTML('afterend',`<span>(since ${low.getFullYear()})</span>`)
      }
    })
    if (xpose.md) { this.mdConverter = new showdown.Converter(xpose.md) }
    this.currentYears = null
    return new FullCalendar.Calendar(divCal,cal)
  }

  events (info,success,failure) {
    var start = new Date(info.start);start=start.getFullYear()
    var end = new Date(info.end);end.setSeconds(end.getSeconds()-1);end=end.getFullYear()
    var years = `${start}-${end}`
    if (this.currentYears==years||this.currentYears=='') {return}
    this.currentYears = ''
    console.log('Loading',years)
    var sql = `SELECT entry as oid,start,end,title,source,
      xpose_template('events/'||Entry.cat||'.xhtml','{"value":'||Entry.value||',"attach":"'||Entry.attach||'"}') as details FROM Event,Entry
      WHERE entry=Entry.oid AND start BETWEEN '${start}-01-01' AND '${end}-12-31' AND source IN (${this.sources}) ORDER BY start DESC
    `
    jQuery.ajax({
      url:this.url,data:{sql:sql},
      success:(data)=>{success(this.process(data));this.currentYears=years},
      failure:(err)=>{failure(err)}
    })
  }

  process (data) {
    this.el_details.innerHTML = ''
    var events = []
    data.forEach((row)=>{
      var ev = {id:`EV-${row.oid}`,start:row.start,end:row.end,title:row.title,extendedProps:{source:row.source}}
      events.push(ev)
      this.el_details.insertAdjacentHTML('beforeend',row.details)
      var tbody = this.el_details.lastElementChild
      tbody.id = ev.id
      var td = tbody.insertRow(0).insertCell()
      td.colSpan = 2; td.className = 'setting'
      var options = this.sourceMap[row.source].options
      Object.entries(options).forEach(([opt,val])=>{ev[opt]=val})
      td.style.backgroundColor = options.backgroundColor||'black'
      td.style.color = options.textColor||'white'
      var extra = tbody.dataset.left||''
      var status = tbody.dataset.right||''
      if (status) {status = `<div class="status">${status}</div>`}
      td.innerHTML = `${moment(row.start).format('llll')} ${extra} ${status}`
    })
    if (this.mdConverter) {
      var mds = this.el_details.getElementsByClassName('md') // treatment of markdown divs
      for (var i=0;i<mds.length;i++) {
        var div = mds[i]
        div.innerHTML = this.mdConverter.makeHtml(div.innerHTML)
        var links = div.getElementsByTagName('a') // forcing http links to open in new window
        for (var j=0;j<links.length;j++) {
          var a = links[j]
          if (new URL(a.getAttribute('href'),this.url).protocol.startsWith('http')) {a.setAttribute('target','_blank')}
        }
      }
    }
    return events
  }
}
