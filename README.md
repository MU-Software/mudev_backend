# [MUdev.cc](https://mudev.cc) Backend Repository <small><small>(with [PlayCo](https://mudev.cc/playco))</small></small>
> This project is based on [MU-Software/frost](https://github.com/MU-software/frost).  
> Check this out if you are interested in building a RESTful API and generating an OpenAPI 3.0 documentation automatically with less code!  

> [여기](README-ko_kr.md)에 한국어 버전의 README가 있어요!  
> [Click here](README-ko_kr.md) to read a README written in Korean.  

> [Click here](https://github.com/MU-Software/mudev_frontend) to visit frontend repository.  

This repository contains the API server code of [MUdev.cc](https://mudev.cc) and [PlayCo](https://mudev.cc/playco) service.

* Currently, MUdev.cc runs on Gunicorn+Eventlet & SQLite & Redis environment behind NGINX reverse proxy.
* Written based on Frost, Please read [MU-Software/frost](https://github.com/MU-software/frost) to see the environment variables and etc.
* To see REST API documentation of MUdev.cc, Please visit [here](https://mudev.cc/doc/dev). Socket.IO API documents are not prepared yet.

## [PlayCo](https://mudev.cc/playco)
PlayCo is a service that uses REST API and Socket.IO to view and modify playlists with others, and to share who is watching which video. Currently, Only logged in users can use the service. (We are preparing for non-login users, so please wait a little bit!)

### PlayCo's Socket.IO Authentication
Events, such as informations about who is watching which video, notification about the modifications of the playlist and its items, are passed through Socket.IO. To use this Socket.IO, an SIO token must be issued and included in each Socket.IO request. This section covers the certification of Socket.IO.

![PlayCo Socket.IO Authentication ](.github/readme/playco_socketio_auth.png)
(This section is currently writing, please wait a little bit...)



# Issues
If you have any questions, or if you found any bugs, please submit an new issue. I'm open to suggestions!
