DROP DATABASE IF EXISTS ouija;

CREATE DATABASE ouija;
USE ouija;

CREATE TABLE IF NOT EXISTS `testjobs` (
  `slave` varchar(64) NOT NULL,
  `result` varchar(32) NOT NULL,
  `duration` int(11) NOT NULL,
  `platform` varchar(32) NOT NULL,
  `buildtype` varchar(32) NOT NULL,
  `testtype` varchar(64) NOT NULL,
  `bugid` text NOT NULL,
  `branch` varchar(64) NOT NULL,
  `revision` varchar(32) NOT NULL,
  `date` datetime NOT NULL,
-- https://treeherder.mozilla.org/api/failureclassification/
  `failure_classification` int(11) NOT NULL,
  `failures` varchar(256) DEFAULT NULL,
  index `revision` (`revision`),
  index `date` (`date`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
