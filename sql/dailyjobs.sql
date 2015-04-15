USE ouija;
CREATE TABLE IF NOT EXISTS `dailyjobs` (
    `date` datetime NOT NULL,
    `platform` varchar(32) NOT NULL,
    `branch` varchar(64) NOT NULL,
    `numpushes` int NOT NULL,
    `numjobs` int NOT NULL,
    `sumduration` int NOT NULL,
    index `date` (`date`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

