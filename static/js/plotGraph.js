function plotGraph(datasets, data_platform) {

    //this function is used to convert the platform name into nice readable headings
    function createHeading(platform) {
        if (platform === 'winxp') return 'Windows XP';
        else if (platform === 'win7') return 'Windows 7';
        else if (platform === 'win8') return 'Windows 8';
        else {
            var d_index = platform.search(/\d/);
            return platform.charAt(0).toUpperCase() + platform.slice(1,d_index) + ' ' + platform.slice(d_index);
        }
    }

    // This function is used to highlighting the weekends in the graph
    function weekendAreas(axes) {
        var markings = [];
        var d = new Date(axes.xaxis.min);

        // go to the first Saturday
        d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 1) % 7));
        d.setUTCSeconds(0);
        d.setUTCMinutes(0);
        d.setUTCHours(0);

        var i = d.getTime();

        // when we don't set yaxis, the rectangle automatically
        // extends to infinity upwards and downwards
        day = 24*60*60*1000;
        do {
            markings.push({ xaxis: { from: i, to: i + 2 * day }});
            i += 7 * day;
        } while (i < axes.xaxis.max);

        return markings;
    }

    var choiceContainer = $("#choices");

    $.each(datasets,function(key,val) {
        if ( key === 'android4.0') {
            html="<br/><input type='radio' name='platform' checked='checked' value='" + key + "'id='id" + key + "'></input>" + "<label for='id" + key + "'>" + createHeading(val.label) + "</label>";
        }
        else {
            html="<br/> <input type='radio' name='platform' value='" + key + "'id='id" + key + "'></input>" + "<label for='id" + key + "'>" + createHeading(val.label) + "</label>";
        }
        choiceContainer.append(html);
    })
    choiceContainer.find("input").click(plotAccordingToChoices);

    var options = {
      xaxis: {
          mode: "time",
          tickLength: 10
      },
      yaxes:[{ min : 0}, { alignTicksWithAxis: 1, position: 'right'}],
      points: {show: true},
      selection: {
          mode: "x"
      },
      lines:{fill: false},
      grid: {
          markings: weekendAreas
      }
    };

    function plotAccordingToChoices() {
      var data = [];
      choiceContainer.find("input:checked").each(function() {
        var key = $(this).attr("value");
        if ( key && datasets[key] ) {
          data.push(datasets[key].data[0]);
          data.push(datasets[key].data[1]);
        }

        $('#heading').text(createHeading(key));
        $('#startDate').text(data_platform[key].dates.startDate.split(" ")[0]);
        $('#endDate').text(data_platform[key].dates.endDate.split(" ")[0]);
      });

      if (data.length > 0) {
        $.plot('#graph',data,options)
      }
    }

    plotAccordingToChoices();
}
