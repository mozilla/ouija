$(function() {
  $error = $("#error"),
  $body = $("body");

  function createDates(data) {
    var s = $('<select />');

    data.sort;

    var count = 0;
    var length = 0;
    for (var val in data) {
       length++;
    }

    var baseline = 0;
    var lastDate = 0;
    for(var val in data) {
      date = val.split(' ')[0];
      count++;
      if (count == 1) {
          baseline = parseInt(data[val]);
          text = date + " (removed: " + baseline + ")";
      } else {
          text = date + " (changed: " + (parseInt(data[val]) - baseline) + ")";
      }
      if (count == length) {
          $('<option />', {value: val, text:text, selected:'selected'}).appendTo(s);
          lastDate = val;
      } else {
          $('<option />', {value: val, text:text}).appendTo(s);
      }
    }
    s.appendTo('body');

    printTable(lastDate);
  }



  function printTable(date) {
    $.getJSON("/data/setadetails/", {date:date}).done(outputTable);
  }

  function printName(testname) {
    retVal = testname.replace('mochitest', 'm');
    retVal = retVal.replace('m-browser-chrome', 'bc');
    retVal = retVal.replace('m-other', 'm-oth');
    retVal = retVal.replace('crashtest-ipc', 'c-ipc');
    retVal = retVal.replace('crashtest', 'c');
    retVal = retVal.replace('jsreftest', 'j');
    retVal = retVal.replace('reftest', 'r');
    retVal = retVal.replace('xpcshell', 'x');
    return retVal;
  }

  function outputTable(data) {
    var dates = data['jobtypes'];
    var os = {};
    for (var date in dates) {
      var tuples = dates[date];
      for (var i=0; i < tuples.length; i++) {
        var tuple = tuples[i];
        var parts = tuple.split('\'');
        osname = parts[1] + " " + parts[3];
        if (os[osname] === undefined) {
          os[osname] = [];
        }
        os[osname].push(parts[5]);
      }
    }

    var oslist = ['linux32', 'linux64', 'osx-10-6', 'osx-10-8', 'windowsxp', 'windows7-32', 'windows8-64'];
    var buildtypes = ['opt', 'debug'];
    var tests = ['mochitest-1', 'mochitest-2', 'mochitest-3', 'mochitest-4', 'mochitest-5', 'mochitest-browser-chrome-1', 'mochitest-browser-chrome-2', 'mochitest-browser-chrome-3', 'mochitest-other', 'xpcshell', 'crashtest', 'crashtest-ipc', 'reftest', 'jsreftest'];
    var mytable = $('<table></table>').attr({id:'seta'});
    for (var o in oslist) {
      for (var b in buildtypes) {
        var row = $('<tr></tr>').appendTo(mytable);
        var key = oslist[o] + " " + buildtypes[b];
        $('<td></td>').text(key).appendTo(row); 
        for (var t in tests) {
          if (os[key] === undefined) {
            continue;
          }
          var pname = printName(tests[t]);
          if (os[key].indexOf(tests[t]) >= 0) {
            $('<td></td>').html('<strike>' + pname + '</strike>').appendTo(row);
          } else {
            $('<td></td>').text(pname).appendTo(row);
          }
        }
      }
    }
    mytable.appendTo('body');
  }

  function done(data) {
    if ($error.is(":visible")) $error.hide();
    createDates(data.dates);
  }

  function fail(error) {
    $dates.hide();
    $error.text(error).show();
  }

  function fetchData(e) {
    if (e) e.preventDefault();
    $.getJSON("/data/setasummary/").done(done).fail(fail);
  }

  $(document).on("ajaxStart ajaxStop", function (e) {
    (e.type === "ajaxStart") ? $body.addClass("loading") : $body.removeClass("loading");
  });

  fetchData();

});
