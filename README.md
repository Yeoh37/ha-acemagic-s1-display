# ACEMAGIC S1 Display for Home Assistant

Application Home Assistant pour afficher l'état de Home Assistant sur l'écran LCD frontal de l'ACEMAGIC S1.

Affichage prévu :

- HOME ASSISTANT
- OK / EN FONCTIONNEMENT
- CPU utilisé
- RAM utilisée
- Heure

Matériel ciblé : écran LCD USB HID `04D9:FD01` du ACEMAGIC S1.


## v1.0.4
Ajout du mode USB direct libusb sur interface 1 / endpoint 0x02.


## 1.0.4

Corrige la construction Docker: installation de PyUSB via pip car le paquet Alpine py3-pyusb est absent dans cette image.
