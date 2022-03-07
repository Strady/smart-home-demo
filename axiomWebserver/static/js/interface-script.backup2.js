const debounceTime = 200;                         // Time to debounce of send data
const host         = "//"+location.host;  // Address to server for sending data
let   socket       = io.connect(host);

document.addEventListener('DOMContentLoaded', function() {
  document.oncontextmenu = function (){return false};

  const statistic = {
    data() {
      return {
        ratio        : 50,
        dataElements : new Array,
        modal        : false,
        legend       : false,
        ctx          : null,
        chartType    : 'polarArea',
        selected     : 0,
        chart        : new Object,
        selectors    : [{
          'name': 'За день',
        },{
          'name': 'За месяц',
        },{
          'name': 'За год',
        }]
      }
    },
    watch: {
      modal(val) {
        this.chartType = val ? 'line' : 'polarArea';
      },
      chartType() {
        this.destroyChart();
        this.InitChart();
        this.chart.update();
      }
    },
    computed: {
      colors() {
        let length      = this.lastData.length;
        let colorsArray = new Array;

        for (var i = 0; i < length; i++) {
          colorsArray.push("rgba("+this.GetRnd(255)+", "+this.GetRnd(255)+", "+this.GetRnd(255)+", 1)")
        }

        return colorsArray;
      },
      lastData() {
        return this.dataElements.map(function(element) {
          return element.values[element.values.length-1]
        })
      },
      labels() {
        return this.dataElements.map(function(element) {
          return element.label
        })
      },
    },
    methods: {
      openModal(event) {
        let selectedPoints = this.chart.getElementsAtEvent(event);
        if (selectedPoints.length > 0) {
          this.selected = selectedPoints[0]._index
          this.modal = true;
        } else {
          this.modal = false;
        }

      },
      destroyChart() {
        let ctx = document.getElementById('circleChart');
        ctx.removeEventListener("contextmenu", this.openModal);
        this.chart.destroy();
      },
      InitChart() {
        let vm      = this;
        let ctx     = document.getElementById('circleChart');
        let config  = new Object;

        config.type    = this.chartType;
        config.options = {
          legend: {
            display : false
          },
          title: {
            display: this.modal,
            text:    this.dataElements[this.selected].label
          },
          responsive : true,
          maintainAspectRatio: false
        };
        config.data    = {
          labels   : this.modal ? this.dataElements[this.selected].values : this.labels,
          datasets : [{
            data : this.modal ? this.dataElements[this.selected].values : this.lastData,
            backgroundColor: this.modal ? this.colors[this.selected] : this.colors
          }]
        };

        console.log(config.data.datasets[0].data);

        vm.chart  = new Chart(ctx.getContext('2d'), config)

        ctx.addEventListener('contextmenu',this.openModal)
      },
      labelPos(angle) {
        if (window.innerWidth>window.innerHeight) {
          if (angle > 255 && angle < 285) {
            return 'top'
          } else if (angle > 80 && angle < 90) {
            return 'bottom'
          } else if (angle > 90 && angle < 255) {
            return 'left'
          } else {
            return 'right'
          }
        } else {
          return 'bottom'
        }

      },
      GetData() {
        this.dataElements.length = 0;

        for (var i = 0; i < app.lights.length; i++) {
          let channel    = new Object;
          channel.label  = app.lights[i].name;
          channel.values = new Array;

          for (var j = 0; j < 4; j++) {
            channel.values.push(this.GetRnd(this.ratio))
          }

          this.dataElements.push(channel)
        }
        this.ctx = document.getElementById('circleChart').getContext('2d');
        this.InitChart();
      },
      GetAngle() {
        return window.innerWidth>window.innerHeight ? 225 : 270
      },
      GetRnd(ratio) {
        return Math.round(Math.random() * ratio);
      }
    },
    mounted() {
      this.GetData();
    },
    template: `
    <z-view v-bind:class='{chart:modal}' style="background-color: #eee !important">
      <div class="chart-container">
        <canvas id="circleChart"></canvas>
      </div>
      <div slot="extension" v-if="!modal">
        <z-spot
          v-for="(selector, index) in selectors"
          @click.native='destroyChart();GetData()'
          :distance="150"
          :angle="120/selectors.length*index+50"
          size='m'>
          {{selector.name}}
        </z-spot>
        <z-spot
          button
          @click.native="legend = !legend"
          :distance="180"
          :angle="GetAngle()"
          label="Легенда"
          size="s"
          labelPos="top">
          {{legend ? "+" : "-"}}
        </z-spot>
        <z-spot
          button
          v-if="legend"
          v-for="(element,index) in dataElements"
          size="xs"
          :angle="360/dataElements.length*index"
          :distance="120"
          @click.native="modal=true;selected=index"
          :label="element.label"
          :labelPos="labelPos(360/dataElements.length*index)"
          v-bind:style="{backgroundColor: colors[index], border: 'none'}">
        </z-spot>
      </div>
    </z-view>`
  }

  // Service Worker registration
  if ('serviceWorker' in navigator) {
      navigator.serviceWorker
      .register('/sw.js')
      .then(function(registration) {
          console.log('Service Worker Registered');
          return registration;
      })
      .catch(function(err) {
          console.error('Unable to register service worker.', err);
      });
  }

  const mainMenu = {
    methods: {
      setView(fromElement,toElement) {
        console.log(this.$zircle);
        app.selectedRoom = null
        app.selected=fromElement;
        this.$zircle.toView({
          to       : toElement,
          fromSpot : this.$refs[fromElement]
        });
      }
    },
    template: `
    <z-view>
      <img src='/img/logo.png' style="width: 90%">
      <div slot="extension">
        <z-spot
          :angle="65"
          :distance="100"
          size="l"
          ref="light"
          @click.native="setView('light','rooms')">
          <i class="fas fa-home" style="font-size: 2.5em;"></i>
        </z-spot>
        <z-spot
          :angle="145"
          :distance="100"
          size="m"
          ref="settings"
          @click.native="setView('settings','settingsMenu')">
          <i class="fas fa-cog" style="font-size: 1.5em;"></i>
        </z-spot>
        <z-spot
          :angle="245"
          :distance="100"
          size="l"
          ref="security"
          @click.native="setView('security','rooms')">
          <i class="fas fa-unlock-alt" style="font-size: 2.5em;"></i>
        </z-spot>
      </div>
    </z-view>`
  }

  const settingsMenu = {
    data: function() {
      return {
        'dialog'   : {
          'show'   : false,
          'message': null,
          'link'   : null
        },
        'elements' : [
          {
            'name' : 'Монтажный интерфейс',
            'link' : '/mount',
            'icon' : 'fa-screwdriver',
            'alert': 'Это приведёт к обeсточиванию всех каналов на уcтройстве. Вы уверены?'
          },
          {
            'name' : 'Панель администратора',
            'link' : '/user',
            'icon' : 'fa-users'
          },
          {
            'name' : 'Ресурсы',
            'link' : 'statistic',
            'icon' : 'fa-chart-pie'
          }
        ]
      }
    },
    methods: {
      Action(element) {
        if (element.alert) {
          this.dialog.show = true;
          this.dialog.link = element.link;
          this.dialog.message = element.alert;
        } else if(element.link[0] == '/'){
          this.FollowTheLink(element.link);
        } else {
          this.$zircle.toView(element.link);
        }
      },
      FollowTheLink(link) {
        window.location.replace(host+link);
        console.log(host+link);
        // window.location.href = host+link;
      }
    },
    template: `
      <z-view>
        <i class="fas fa-cog" style="font-size: 5em; color: white;"></i>
        <div slot="extension">

          <z-spot
            v-for="(element, index) in elements"
            :ref="index"
            :angle="360 / elements.length * index"
            @click.native="Action(element)"
            size="l"
            :label="element.name">
            <i class="fas" :class="element.icon" style="font-size: 2.5em;"></i>
          </z-spot>

          <z-dialog v-if="dialog.show" v-on:done="dialog.show = false">
            <i class="fas fa-exclamation-triangle" style="font-size:3em;"></i><br>
            {{dialog.message}}
            <div slot='extension'>
              <z-spot
                button
                :distance='120'
                :angle='45'
                size='m'
                @click.native='FollowTheLink(dialog.link); dialog.show=false'>
                Да
              </z-spot>
              <z-spot
                button
                :distance='120'
                :angle='135'
                size='m'
                @click.native='dialog.show=false'>
                Нет
              </z-spot>
            </div>
          </z-dialog>

        </div>
      </z-view>`
  }

  const rooms = {
    data: function() {
      return  {
        'rooms'   : app.getSubTypes,
        'selected': app.selected
      }
    },
    computed: {
      icon() {
        switch (this.selected) {
          case 'light':
            return 'fa-home'
            break;
          case 'security':
            return 'fa-unlock-alt'
            break;
        }
      }
    },
    methods: {
      setView(fromElement,toElement) {
        console.log(this.$refs[fromElement.ref]);
        if (this.selected === 'security') {
          app.selected = fromElement.name;
        } else {
          app.selectedRoom = fromElement.name;
        }
        this.$zircle.toView(toElement);
        // this.$zircle.toView({
        //   to       : toElement,
        //   fromSpot : this.$refs[fromElement.ref]
        // });
      },
      getName(name) {
        switch (name) {
          case 'water':
            return 'Водообеспечение'
            break;
          case 'perimeter':
            return 'Периметр'
            break;
          default:
            return name
        }
      }
    },
    template: `
    <z-view>
      <i class="fas" :class="icon" style="font-size:4em; color: white;"></i>
      <div slot="extension">
        <z-spot
          v-for="(room, index) in rooms"
          :angle="360/rooms.length*index"
          size="l"
          :label="getName(room.name)"
          :ref="room.ref"
          @click.native="setView(room,'elements')">
        </z-spot>
      </div>
    </z-view>`
  }

  const elements = {
    data: function() {
      return {
        'elements'     : app.itemsList(app.selected),
        'selectedDimm' : null,
        'room'         : app.selectedRoom,
        'selected'     : app.selected,
        'canSend'      : app.canSend,
        'oldElements'  : new Object,
        'dialog' : {
          'show'    : false,
          'message' : null,
          'target'  : null
        }
      }
    },
    computed: {
      selectedTranslated() {
        switch (this.selected) {
          case 'light':
            return 'Освещение'
            break;
          case 'water':
            return 'Водообеспечение'
            break;
          case 'perimeter':
            return 'Периметр'
            break;
          default:
            return 'Элементы управления'
        }
      }
    },
    watch: {
      elements: {
        handler(value) {
          let vm = this;
          console.log('can send is',app.canSend);
          value.forEach(function(currentVal) {
            let ifQty    = currentVal.qty    != vm.oldElements[currentVal.id].qty;
            let ifStatus = currentVal.status != vm.oldElements[currentVal.id].status;

            if (ifQty || ifStatus) {
              vm.oldElements[currentVal.id].qty    = currentVal.qty;
              vm.oldElements[currentVal.id].status = currentVal.status;

              if (app.canSend) {
                vm.sendData(currentVal);
              }
              app.canSend = true;
            }
          })
        },
        deep: true
      }
    },
    methods: {
      getAngle(element) {
        let elementsOfRoom = (this.room == null) ? this.elements : this.elements.filter(element => element.room == this.room);
        let index = elementsOfRoom.indexOf(element);
        return 360 / elementsOfRoom.length * index;
      },
      sendData: _.debounce(function(value) {
        let data = {
          'id'  : value.id,
          'type': this.selected,
          'state': {
            'status': value.status,
            'value' : value.qty
          }
        }
        socket.emit('pushdata', data);
        console.log('push to',data);
      }, debounceTime),

      getIcon(element) {
        let icon = new Object;

        switch (this.selected) {
          case 'light':
            icon.name  = 'fa-lightbulb';
            icon.color = element.status ? 'var(--active-color)' : 'var(--unactive-color)';
            break;
          case 'water':
            switch (element.we_type) {
              case 'indicator':
                icon.name  = element.status ? 'fa-exclamation-triangle' : 'fa-check-circle';
                icon.color = element.status ? 'yellow' : 'var(--unactive-color)';
                break;
              case 'checkbox':
                icon.name  = element.status ? 'fa-tint' : 'fa-tint-slash';
                icon.color = element.status ? 'var(--active-color)' : 'var(--unactive-color)';
                break;
            }
            break;
          case 'perimeter':
            switch (element.we_type) {
              case 'indicator':
                icon.name  = element.status ? 'fa-check-circle' : 'fa-exclamation-triangle';
                icon.color = element.status ? 'var(--active-color)' : 'yellow';
                break;
            }
            break;
          default:
            icon.name  = element.status ? 'fa-check-circle' : 'fa-times-circle';
            icon.color = element.status ? 'var(--active-color)' : 'var(--unactive-color)';
        }

        return icon;
      },

      getBorderColor(element) {
        if (!element.status) {
          return 'var(--unactive-color)'
        } else { return 'var(--active-color)' }
      },

      action(index) {
        let element = this.elements[index];
        console.log(element.we_type)
        switch (element.we_type) {
          case 'indicator':
            break;
          case 'range':
            this.selectedDimm = index;
            console.log(element);
            break;
          default:
            let addr   = element.id;
            let childs = this.elements.filter(child => child.parent == addr && child.status == true);

            if ((childs.length > 0) <= element.status) {
              element.status = !element.status;
            } else {
              let childsName = childs.map(child => child.name).join(',');

              this.dialog.show    = true;
              this.dialog.message = 'Датчики (' + childsName + ') всё ещё активны, вы уверены?';
              this.dialog.target  = index;
            }
        }
      }
    },
    mounted() {
      let vm = this;
      console.log('selectedRoom is', this.room)
      vm.elements.forEach(function(value) {
        vm.oldElements[value.id]        = new Object;
        vm.oldElements[value.id].qty    = value.qty;
        vm.oldElements[value.id].status = value.status;
      })
      console.log(vm.oldElements);
    },
    template: `
      <z-view>
        {{selectedTranslated}}<br><span v-if="room">в "{{room}}"</span>
        <div slot="extension">
          <z-spot
            v-if="selectedDimm != null"
            :distance="0"
            size="xl"
            knob
            v-bind.sync="element"
            v-bind:style='{"border-color": getBorderColor(element)}'
            v-bind.sync="elements[selectedDimm]">
            <z-spot
              slot="extension"
              button
              :distance="0"
              style="border:none;"
              @click.native="elements[selectedDimm].status = !elements[selectedDimm].status"
              v-bind:style='{color: getIcon(elements[selectedDimm]).color}'
              v-bind:class='getIcon(elements[selectedDimm]).name'>
              <i
                class='fa'
                style='font-size: 2em;'>
              </i><br>
              {{elements[selectedDimm].name}}
            </z-spot>
          </z-spot>

          <z-spot
            :distance="110"
            v-for="(element,index) in elements"
            v-if="element.room == room || room == null"
            :angle="getAngle(element)"
            :label="element.name"
            v-bind:style='{"border-color": getBorderColor(element)}'
            size="m">
            <z-spot
              slot="extension"
              button
              :distance="0"
              style="border:none;"
              size="s"
              @click.native="action(index)">
                <i
                  class='fa'
                  style='font-size: 1.5em;'
                  v-bind:style='{color: getIcon(element).color}'
                  v-bind:class='getIcon(element).name'>
                </i>
            </z-spot>
          </z-spot>

          <z-dialog v-if="dialog.show" v-on:done="dialog.show = false">
            <i class="fas fa-exclamation-triangle"></i><br>
            {{dialog.message}}
            <div slot='extension'>
              <z-spot
                button
                :distance='120'
                :angle='45'
                size='m'
                @click.native='elements[dialog.target].status=true; dialog.show=false'>
                Да
              </z-spot>
              <z-spot
                button
                :distance='120'
                :angle='135'
                size='m'
                @click.native='dialog.show=false'>
                Нет
              </z-spot>
            </div>
          </z-dialog>
        </div>
      </z-view>
    `
  }

  var app = new Vue({
    el: '#app',
    data: {
      lights       : new Array,
      water        : new Array,
      perimeter    : new Array,
      rooms        : new Array,
      selected     : null,
      selectedRoom : null,
      canSend      : true
    },
    computed: {
      getSubTypes() {
        switch (this.selected) {
          case 'security':
            return [
              {
                'name' : 'water',
                'ref'  : 'water'
              },
              {
                'name' : 'perimeter',
                'ref'  : 'perimeter'
              }
            ]
            break;
          default:
            return this.rooms
        }
      }
    },
    methods: {
      itemsList(itemsType) {
        switch (itemsType) {
          case "water":
            return this.water
            break;
          case "perimeter":
            return this.perimeter
            break;
          default:
            return this.lights;
        }
      },
      setData(msg) {
        // vm.canSend = false;
        // let list = vm.itemsList(msg.type);
        let type = 'light';
        if (this.itemsList(type).filter(item => item.id == msg.id) == 0) {
          type = 'water';
          if (this.itemsList(type).filter(item => item.id == msg.id) == 0) {
            type = 'perimeter';
          }
        }

        for (index in this.itemsList(type)) {
          if (this.itemsList(type)[index].id == msg.id) {
            let status = msg.state.status != undefined ? msg.state.status : this.itemsList(type)[index].status;
            let value  = msg.state.value  != undefined ? msg.state.value : this.itemsList(type)[index].qty;

            this.itemsList(type)[index].status = status;
            this.itemsList(type)[index].qty    = value;

            break;
          }
        }
        // vm.canSend = true;
      }
    },
    watch: {
      selected() {
        console.log(this.$zircle);
        // this.$zircle.toView('elements');
      }
    },
    components: {
      mainMenu, elements, rooms, settingsMenu, statistic
    },
    mounted () {
      const vm = this;

      vm.$zircle.config({
  		  debug: true
  	  });

      // socket = io.connect(host);
      console.log('host is', host);

      axios
        .get(host+'/api/markup')
        .then(responce => {
            console.log('msg is',responce.data);
            let rooms = vm.rooms;

            for (index in responce.data) {
              let value   = responce.data[index];
              let element = {
                'name'    : value.name,
                'id'      : value.addr,
                'room'    : value.room,
                'status'  : value.state.status,
                'we_type' : value.we_type,
                'qty'     : value.state.value,
                'parent'  : value.parent
              }

              //Добавление комнат (разобраться позже с тем, чтобы сделать из этого вычисляемое свойство или метод)
              if (value.room && rooms.filter(room => room.name == value.room) == 0) {
                let newRoom = {
                  'name' : value.room,
                  'ref'  : 'room'+rooms.length
                }
                rooms.push(newRoom)
              }
              vm.itemsList(value.type).push(element);

            }
            console.log(vm);

            vm.$zircle.setView('mainMenu');
        })
        .catch(err => {
          if (err.response.status == 401) {
            location.href = host + '/login'
          }
        });

      socket.on('state change',function(msg) {
        console.log('state change', msg);
        vm.setData(msg);
      });

      socket.on('pushback',function(msg) {
        console.log('pushback', msg);
        vm.setData(msg);
      });
    }
  })
})
