const host = location.host;
//const host = 'http://192.168.1.156:5000'; 
var socket = io.connect(host);

document.addEventListener("DOMContentLoaded", function() {
	Vue.component('hat', {
		template: '#hat',
		props: {
			title: String
		}
	})

	Vue.component('greeting', {
		template: '#greeting',
		props: {
			text: Object
		}
	})

	Vue.component('mount', {
		template: '#mount',
		props: {
			channel: Object
		}
	})

	var app = new Vue({
		el: '#app',
		data: {
			status: 'starting',
			channels: [],
			index: 0
		},
		computed: {
			title: function() {
				if (this.status == 'mounting') {
					return "Монтаж"
				} else if (this.status == 'ending') {
					return "Завершение"
				} else {
					return "Добро пожаловать!"
				}
			},
			greeting : function () {
				var data = {};

				if (this.status == 'starting') {
					data.text = `
						Добро пожаловать в монтажный интерфейс AXIOM! Для проведения монтажа данного устройства, вам потребуется:
						<ul>
							<li>Отвёртка</li>
							<li>Обжимной инструмент</li>
							<li>Базовые знания электромонтажа</li>
						</ul>`
					data.buttontext = 'Начать'
				} else {
					data.text = `Монтаж завершён! Для начала работы, нажмите на кнопку`
					data.buttontext = 'Приступить к работе'
				}
				return data;
			}
		},
		mounted: function() {
			socket.on('getData', function (msg) {
				console.log('i got the message!',msg);

				var data = [],
					msgKeys = Object.keys(msg),
					msgValues = Object.values(msg);

				//Hardcode (adding first step)
				// data.push({
				// 	name: 'Левый верхний (синий) контакт колодки',
				// 	channel: 'channel1'
				// },{
				// 	name: 'Левым нижний (оранжевый) контакт колодки',
				// 	channel: 'channel2'
				// })

				msgKeys.forEach(function (name, index) {
					data.push({
						'name': name,
						'channel': msgValues[index]
					})
				})

				console.log('unsorted: ',data)

				data.sort(function(a,b) {
					if (a.channel > b.channel) {
						return 1;
					}
					if (a.channel < b.channel) {
						return -1;
					}
					return 0;
				})

				console.log('sorted: ',data)

				app.channels = data;
			})
			
			socket.emit('ready for mounting');
		},
		methods: {
			greetingButton: function() {
				if (this.status == 'starting') {
					// console.log(this.channels[this.index].channel)
					try	{
						this.status = 'mounting';

						console.log(this.channels[0].channel)
						socket.emit('blink', this.channels[0].channel);
					} catch(err) {
						console.log('Возникла ошибка:',err)
					}
				} else { window.location.href = "https://app.ttechnika.ru/" }
			},
			nextChannel: function() {
				if (this.channels[this.index+1] != undefined) {
					this.index++;
					try	{
						console.log(this.channels[this.index].channel)
						socket.emit('blink', this.channels[this.index].channel);
					} catch(err) {
						console.log('Не удалось отправить данные', err)
					}
				} else {
					socket.emit('blink', 'lights off');
					this.status = 'ending';
				}
			}
		}
	})
});
