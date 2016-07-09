USE ouija;

CREATE TABLE IF NOT EXISTS `seta` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `jobtype` varchar(256) NOT NULL,
  `date` datetime NOT NULL,
  primary key(id)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
